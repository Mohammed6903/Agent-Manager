"""Third-party context auto-injection for chat turns.

This module owns the "pre-fetch relevant chunks from the user's
connected integrations and drop them into the system prompt" path —
the read side of the third-party RAG pipeline. The ingestion side
(Gmail/Drive/Notion/etc. Celery tasks) lives elsewhere; this file
only reads from the Qdrant index those jobs populate.

## Why it exists in this shape

The previous version of this module ran one semantic search PER
connected source (gmail + drive + slack + ...) plus a "snapshot"
fetch per source, then concatenated everything into a ~4000-char
block. That scaled linearly with integration count and produced
unsustainable prompt bloat on busy agents. It was removed from the
chat path entirely for several weeks because of that cost.

This rewrite matches the same hybrid pattern ``manual_context_service``
uses:

- **One** embedding call + **one** Qdrant query, unified across all
  third-party sources (Qdrant filters by ``agent_id`` and excludes
  ``source="manual_context"``).
- **Relevance gate** — if the top-1 chunk's similarity score is below
  ``MIN_RELEVANCE_SCORE``, skip injection entirely. Unrelated chat
  turns ("hi", "what's 2+2") pay only the cheap embedding cost, no
  prompt tokens.
- **Hard char cap** at ``MAX_BLOCK_CHARS`` so the block size is
  constant regardless of how much data the agent has indexed.
- **Inline source labels** per chunk (``From Gmail — "Re: ..."``)
  instead of per-source section headers. Works for any number of
  sources without adding fixed overhead.
- **No more snapshot fetches** — the per-source ``latest N items``
  behavior is gone. If the user asks "what's new in my inbox?" the
  agent should call a ``gmail_latest`` tool explicitly.

## Cost per chat turn (approximate)

- 1 Postgres query (assignment lookup, <1ms)
- 1 embedding call (~5ms, ~$0.000005 for ``text-embedding-3-small``)
- 1 Qdrant query (<10ms)
- Up to ~400 tokens of prompt tax (only on turns that actually match)

That's constant regardless of whether the agent has 2 integrations
or 20.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy.orm import Session

from ..repositories.third_party_context_assignment_repository import (
    ThirdPartyContextAssignmentRepository,
)
from . import embed_service, qdrant_service

logger = logging.getLogger(__name__)

# ── Auto-inject tuning ──────────────────────────────────────────────────────
# Calibrated for ``text-embedding-3-small``. Same threshold the manual
# context auto-inject uses — below this, the top-1 chunk is typically
# only tangentially related and including it just costs tokens without
# improving the answer.
MIN_RELEVANCE_SCORE = 0.35

# Top-3 matches per turn. Slightly tighter than the manual-context
# top-3 because third-party content tends to be noisier (email
# threads, doc snippets from unrelated sections) and top-3 is already
# enough coverage — deeper dives should be explicit tool calls.
AUTO_INJECT_TOP_K = 3

# Hard char cap on the entire rendered block (header + chunks + footer).
# ~1500 chars ≈ 375 tokens. Combined with manual-context's 2000-char
# cap, the worst-case combined injection is ~3500 chars / ~875 tokens
# per turn — about a third of the old per-source-parallel-query cost.
MAX_BLOCK_CHARS = 1500

# Per-chunk text truncation. Even if one chunk fits inside MAX_BLOCK_CHARS
# on its own, a ~800-char snippet is enough context for the model to
# answer from; longer just wastes tokens. Truncated chunks get an
# ellipsis marker so the model knows there's more if it wants to dig
# via an explicit tool call.
MAX_CHARS_PER_CHUNK = 600

# Label mapping from the ``source`` slug stored in Qdrant payloads to
# a human-friendly display name for the inline chunk header. Unknown
# slugs fall back to ``source.title()``.
_SOURCE_DISPLAY_NAMES = {
    "gmail": "Gmail",
    "google_gmail": "Gmail",
    "google_docs": "Google Docs",
    "google_drive": "Google Drive",
    "google_calendar": "Google Calendar",
    "outlook": "Outlook",
    "microsoft_outlook": "Outlook",
    "notion": "Notion",
    "slack": "Slack",
    "discord": "Discord",
    "github": "GitHub",
    "linear": "Linear",
    "jira": "Jira",
    "confluence": "Confluence",
}

# Fields that can carry the chunk's text content, tried in order of
# preference. Different ingestion pipelines use different key names
# and this list covers everything I've seen in the existing
# integrations. If none are present the chunk is dropped.
_TEXT_FIELDS = ("text", "snippet", "content", "body", "excerpt")

# Fields that can serve as a display title/label for a chunk (e.g.
# email subject, doc title, file name). First non-empty one wins.
_TITLE_FIELDS = (
    "title",
    "subject",
    "name",
    "filename",
    "file_name",
    "display_name",
)


def _source_display(source: str) -> str:
    """Turn a source slug into a human-readable label."""
    s = (source or "").strip().lower()
    if not s:
        return "integration"
    return _SOURCE_DISPLAY_NAMES.get(s, s.replace("_", " ").title())


def _chunk_text(chunk: dict[str, Any]) -> str:
    """Extract the best text field from a Qdrant payload."""
    for field in _TEXT_FIELDS:
        val = chunk.get(field)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _chunk_title(chunk: dict[str, Any]) -> str:
    """Extract a display title from a Qdrant payload, or empty string."""
    for field in _TITLE_FIELDS:
        val = chunk.get(field)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _format_chunk(chunk: dict[str, Any]) -> str:
    """Render one chunk as a markdown block with inline source label.

    Returns an empty string if the chunk has no usable text content
    — the caller drops it.
    """
    text = _chunk_text(chunk)
    if not text:
        return ""
    if len(text) > MAX_CHARS_PER_CHUNK:
        text = text[: MAX_CHARS_PER_CHUNK - 3].rstrip() + "…"

    source_label = _source_display(str(chunk.get("source") or ""))
    title = _chunk_title(chunk)

    if title:
        header = f'From {source_label} — "{title}":'
    else:
        header = f"From {source_label}:"

    return f"{header}\n{text}"


async def build_context_block(
    db: Session,
    agent_id: str,
    user_message: str,
    query_vector: list[float] | None = None,
) -> str | None:
    """Build a system-prompt block for third-party context auto-injection.

    Called by ``chat_service`` on every turn (streaming and
    non-streaming) before forwarding to the gateway.

    The optional ``query_vector`` parameter lets the caller pre-compute
    the user-message embedding once and share it between this function
    and the manual-context auto-inject path (they both embed the same
    text, so caching the result across both calls saves one API round
    trip per chat turn). If ``None``, this function embeds the message
    itself.

    Returns ``None`` (skip injection) when:

    - The user message is empty/whitespace-only
    - The agent has no third-party context assignments at all
    - The embedding call fails
    - The Qdrant search returns nothing
    - The top-1 chunk's similarity score is below ``MIN_RELEVANCE_SCORE``
      (the cheap relevance gate — saves ~400 tokens/turn on small
      talk and unrelated questions where no integration actually
      matches)

    Otherwise returns a formatted string ready for insertion as a
    ``{"role": "system", "content": ...}`` message. Bounded to
    ``MAX_BLOCK_CHARS`` chars total.
    """
    if not user_message or not user_message.strip():
        return None

    # Cheap pre-check: if the agent has no connected integrations at
    # all, skip the embedding call entirely. Matches the manual-context
    # pattern.
    assign_repo = ThirdPartyContextAssignmentRepository(db)
    contexts = assign_repo.get_contexts_for_agent(agent_id, status="complete")
    if not contexts:
        return None

    loop = asyncio.get_running_loop()
    if query_vector is None:
        # Run the embed call in a worker thread — ``embed_service.embed_single``
        # is synchronous (it drives Redis TPM tracking + HTTP calls inline)
        # and we don't want to block the FastAPI event loop on it.
        try:
            query_vector = await loop.run_in_executor(
                None, embed_service.embed_single, user_message
            )
        except Exception:
            logger.exception(
                "Query embedding failed for third-party auto-inject (agent=%s)",
                agent_id,
            )
            return None

    # Unified search — ONE query across all third-party sources for
    # this agent. Excludes manual-context chunks via ``must_not`` so
    # the third-party and manual auto-inject blocks don't double-count.
    try:
        hits = await loop.run_in_executor(
            None,
            lambda: qdrant_service.search_third_party(
                agent_id=agent_id,
                query_vector=query_vector,
                top_k=AUTO_INJECT_TOP_K,
            ),
        )
    except Exception:
        logger.exception(
            "Qdrant third-party search failed (agent=%s)", agent_id
        )
        return None

    if not hits:
        return None

    # Relevance gate: if even the best chunk is below threshold, the
    # user's message has no semantic match in any of their integrations
    # for this turn. Skip injection entirely.
    top_score = max((h.get("score") or 0.0) for h in hits)
    if top_score < MIN_RELEVANCE_SCORE:
        logger.debug(
            "Third-party auto-inject skipped (top_score=%.3f < %.3f) for agent=%s",
            top_score,
            MIN_RELEVANCE_SCORE,
            agent_id,
        )
        return None

    relevant = [
        h for h in hits if (h.get("score") or 0.0) >= MIN_RELEVANCE_SCORE
    ]
    if not relevant:
        return None

    # Format each relevant chunk with an inline source label + title
    # (if present) + body text. Drop any chunk whose payload has no
    # usable text field.
    formatted_chunks = [c for c in (_format_chunk(h) for h in relevant) if c]
    if not formatted_chunks:
        return None

    header = (
        "[CONNECTED ACCOUNTS — pre-fetched]\n"
        "The following excerpts were retrieved from the user's connected "
        "integrations via semantic search on their latest message. Use "
        "them when relevant to answer accurately. If they don't address "
        "the question, ignore them and answer normally — do NOT force "
        "them into an unrelated answer.\n\n"
    )
    footer = "[END CONNECTED ACCOUNTS]"
    fixed_overhead = len(header) + len(footer)
    available = MAX_BLOCK_CHARS - fixed_overhead

    parts: list[str] = []
    used = 0
    for chunk_block in formatted_chunks:
        # The chunk separator is a blank line, same as the manual-context
        # block. Accounts for two newlines between consecutive chunks.
        piece = chunk_block + "\n\n"
        if used + len(piece) <= available:
            parts.append(piece)
            used += len(piece)
            continue
        # Doesn't fit — try truncating this chunk to fill the remainder.
        # Only worth it if there's enough room left for a meaningful
        # fragment (header + ~100 chars of body), otherwise stop.
        remaining = available - used
        if remaining < 150:
            break
        truncate_marker = "…[truncated]"
        body_room = remaining - len(truncate_marker) - 2  # 2 for trailing \n\n
        if body_room > 50:
            parts.append(chunk_block[:body_room].rstrip() + truncate_marker + "\n\n")
        break

    if not parts:
        return None

    block = header + "".join(parts).rstrip() + "\n" + footer

    logger.info(
        "Third-party auto-inject: agent=%s top_score=%.3f chunks=%d chars=%d sources=%s",
        agent_id,
        top_score,
        len(parts),
        len(block),
        ",".join(sorted({str(h.get("source") or "?") for h in relevant})),
    )
    return block
