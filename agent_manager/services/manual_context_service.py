"""Manual-context RAG pipeline: chunk → embed → Qdrant store + search.

Manual contexts (``GlobalContext``) are user-provided knowledge documents
that can be assigned to any number of agents. Unlike third-party contexts
(Gmail, Drive, etc.), they're NOT auto-injected into every chat turn —
token cost scales poorly with many plugins, so retrieval is explicit: the
client (or a future agent tool) hits the search endpoint when it decides
it needs to look something up.

This module owns:

- **Chunking**: character-window with overlap (sufficient for FAQs,
  handbooks, policies, and most prose knowledge). No sentence/paragraph
  awareness yet — can be upgraded later if needed.
- **Hashing**: SHA-256 of content so we can skip re-embedding on
  rename-only edits.
- **Embedding**: delegates to ``embed_service`` (OpenAI or Gemini,
  configurable). Sync, inline with the API call — typical manual contexts
  are small enough that a blocking embed is fine.
- **Qdrant upsert/delete**: via ``qdrant_service``'s new manual-context
  helpers. Points are keyed by ``context_id`` (not ``agent_id``) because
  manual contexts are globals shared across agents.
- **Retrieval**: ``search_for_agent`` resolves "what contexts is this
  agent assigned?" from Postgres, then vector-searches those in Qdrant.

Wiring:

- ``ContextService`` calls ``index_context`` / ``reindex_context`` /
  ``delete_context_chunks`` at the appropriate CRUD hooks.
- The context router exposes ``/search`` and ``/reindex`` HTTP endpoints
  that wrap the functions here.
- Chat/voice code does NOT auto-inject. If you want manual context in a
  prompt, you explicitly call the search endpoint (or a future tool).
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any

from qdrant_client.models import PointStruct
from sqlalchemy.orm import Session

from ..repositories.context_repository import ContextRepository
from . import embed_service, qdrant_service

logger = logging.getLogger(__name__)

# ── Chunking parameters ──────────────────────────────────────────────────────
# Character-based window. ~800 chars ≈ ~200 tokens per chunk at typical
# English density. Overlap of 100 chars helps preserve semantic continuity
# across chunk boundaries so a phrase that straddles a boundary still
# surfaces in at least one chunk's embedding.
CHUNK_SIZE_CHARS = 800
CHUNK_OVERLAP_CHARS = 100

# Retrieval defaults. Top-5 is the industry norm for RAG over small
# corpora; lower values risk missing the answer, higher values inflate
# the payload the caller has to carry around.
DEFAULT_TOP_K = 5


def compute_content_hash(content: str) -> str:
    """Stable fingerprint for change detection on update."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def chunk_text(content: str) -> list[dict[str, Any]]:
    """Split content into overlapping character windows.

    Returns a list of ``{"chunk_index": int, "text": str}`` dicts,
    preserving order. Empty / whitespace-only input returns an empty list.

    Overlap logic: advance by ``CHUNK_SIZE_CHARS - CHUNK_OVERLAP_CHARS``
    each step, so consecutive chunks share ``CHUNK_OVERLAP_CHARS`` chars
    at their boundary. The final chunk may be shorter than
    ``CHUNK_SIZE_CHARS``.
    """
    if not content or not content.strip():
        return []
    stride = CHUNK_SIZE_CHARS - CHUNK_OVERLAP_CHARS
    if stride <= 0:
        stride = CHUNK_SIZE_CHARS  # defensive: overlap >= size is nonsense
    chunks: list[dict[str, Any]] = []
    cursor = 0
    idx = 0
    while cursor < len(content):
        end = min(cursor + CHUNK_SIZE_CHARS, len(content))
        text = content[cursor:end].strip()
        if text:
            chunks.append({"chunk_index": idx, "text": text})
            idx += 1
        if end >= len(content):
            break
        cursor += stride
    return chunks


def index_context(
    context_id: uuid.UUID,
    name: str,
    content: str,
) -> int:
    """Chunk + embed + upsert a GlobalContext into Qdrant.

    Idempotent at the Qdrant level — Qdrant upserts by point id, and the
    point ids here are derived deterministically from ``(context_id,
    chunk_index)``, so re-running on the same content overwrites in place
    instead of creating duplicates. However, if ``content`` changes the
    chunk boundaries shift, and old (now-orphaned) chunks at higher
    indices will not be cleaned up — callers that do content updates
    should use ``reindex_context`` instead (delete-then-insert).

    Returns the number of chunks indexed. Zero if content was empty.
    """
    chunks = chunk_text(content)
    if not chunks:
        return 0

    texts = [c["text"] for c in chunks]
    try:
        vectors = embed_service.embed_texts(texts)
    except Exception:
        logger.exception(
            "Embedding failed for manual context %s (%s)", context_id, name
        )
        raise

    if len(vectors) != len(chunks):
        # embed_service is contracted to preserve order; if this happens
        # something upstream is broken and we should not silently truncate.
        raise RuntimeError(
            f"Embedding count mismatch for context {context_id}: "
            f"{len(chunks)} chunks vs {len(vectors)} vectors"
        )

    ctx_id_str = str(context_id)
    points: list[PointStruct] = []
    for chunk, vector in zip(chunks, vectors):
        # Deterministic point id: UUID5 over (context_id, chunk_index).
        # Same inputs → same id, so re-indexing the same content overwrites
        # existing points rather than accumulating duplicates.
        point_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"manual_context:{ctx_id_str}:{chunk['chunk_index']}",
            )
        )
        points.append(
            PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "source": qdrant_service.MANUAL_CONTEXT_SOURCE,
                    "context_id": ctx_id_str,
                    "context_name": name,
                    "chunk_index": chunk["chunk_index"],
                    "text": chunk["text"],
                },
            )
        )

    qdrant_service.upsert_points(points)
    logger.info(
        "Indexed manual context %s (%s): %d chunks",
        context_id,
        name,
        len(points),
    )
    return len(points)


def reindex_context(
    context_id: uuid.UUID,
    name: str,
    content: str,
) -> int:
    """Delete all existing chunks for a context and re-index from scratch.

    Use this on content updates. ``index_context`` alone is NOT sufficient
    because the new chunk count may be less than the old one, leaving
    orphaned chunks in Qdrant.
    """
    delete_context_chunks(context_id)
    return index_context(context_id, name, content)


def delete_context_chunks(context_id: uuid.UUID) -> int:
    """Remove all Qdrant points for a manual context.

    Called by ContextService.delete_global_context and by reindex_context.
    Returns the number of points deleted. Safe to call on a context that
    was never indexed (returns 0).
    """
    try:
        return qdrant_service.delete_points_for_context(str(context_id))
    except Exception:
        logger.exception(
            "Failed to delete Qdrant chunks for manual context %s", context_id
        )
        return 0


def backfill_unindexed_contexts(db: Session) -> dict[str, int]:
    """Index every ``GlobalContext`` with a NULL ``content_hash``.

    Used for (a) migrating pre-RAG contexts that existed before this
    pipeline was introduced and (b) retrying contexts whose original
    index attempt failed (the create/update paths leave content_hash
    NULL on failure so this sweep picks them up on the next run).

    Each context is processed independently: a single failure is logged
    and the sweep continues. Embedding rate limits are handled inside
    ``embed_service`` via its Redis-backed TPM counter, so running this
    on a large corpus self-throttles rather than tripping 429s.

    Returns a dict with ``{scanned, indexed, skipped, failed}`` counts
    — useful for both the admin endpoint and the startup log line.
    """
    from ..models.context import GlobalContext  # local import to avoid cycles

    rows = (
        db.query(GlobalContext)
        .filter(GlobalContext.content_hash.is_(None))
        .all()
    )

    stats = {"scanned": len(rows), "indexed": 0, "skipped": 0, "failed": 0}
    if not rows:
        return stats

    for ctx in rows:
        if not ctx.content or not ctx.content.strip():
            # Empty content — mark as "indexed" with a zero-chunk hash so
            # we don't retry this row forever on every backfill sweep.
            ctx.content_hash = compute_content_hash(ctx.content or "")
            stats["skipped"] += 1
            continue
        try:
            index_context(ctx.id, ctx.name, ctx.content)
            ctx.content_hash = compute_content_hash(ctx.content)
            stats["indexed"] += 1
        except Exception:
            logger.exception(
                "Backfill failed for context %s (%s) — leaving content_hash NULL for retry",
                ctx.id,
                ctx.name,
            )
            stats["failed"] += 1

    # Commit once at the end so partial-progress hash updates survive a
    # subsequent crash. If we crashed mid-loop, already-processed rows
    # would still be NULL on next startup and get retried — acceptable.
    try:
        db.commit()
    except Exception:
        logger.exception("Backfill commit failed — content_hash updates lost")
        db.rollback()

    logger.info(
        "Manual context backfill complete: scanned=%d indexed=%d skipped=%d failed=%d",
        stats["scanned"],
        stats["indexed"],
        stats["skipped"],
        stats["failed"],
    )
    return stats


def search_for_agent(
    db: Session,
    agent_id: str,
    query: str,
    top_k: int = DEFAULT_TOP_K,
) -> list[dict[str, Any]]:
    """Retrieve top-k manual-context chunks for an agent's query.

    Two-stage lookup:

    1. Postgres: fetch the list of ``GlobalContext`` ids assigned to this
       agent via the ``agent_contexts`` junction table.
    2. Qdrant: semantic search over manual-context points filtered by
       that id list, using an embedding of ``query``.

    Returns a list of dicts with ``score``, ``context_id``, ``context_name``,
    ``chunk_index``, and ``text``. Empty list if the agent has no assigned
    contexts, the query is empty, or embedding fails.

    Intentionally does NOT inject into any prompt — retrieval is explicit
    and the caller decides what to do with the chunks.
    """
    if not query or not query.strip():
        return []

    repo = ContextRepository(db)
    contexts = repo.get_assigned_contexts_for_agent(agent_id)
    if not contexts:
        return []

    context_ids = [str(c.id) for c in contexts]

    try:
        query_vector = embed_service.embed_single(query)
    except Exception:
        logger.exception(
            "Query embedding failed for manual context search (agent=%s)",
            agent_id,
        )
        return []

    results = qdrant_service.search_manual_context(
        context_ids=context_ids,
        query_vector=query_vector,
        top_k=top_k,
    )
    return results
