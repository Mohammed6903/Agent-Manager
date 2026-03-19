"""Assemble third-party context blocks for injection into chat prompts."""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from ..repositories.third_party_context_assignment_repository import (
    ThirdPartyContextAssignmentRepository,
)
from ..services import embed_service, qdrant_service
from ..services.context_providers import get_provider

logger = logging.getLogger(__name__)

# Hard cap on injected context to control token cost.
_MAX_CONTEXT_CHARS = 4000  # ~1000 tokens at ~4 chars/token
_SNIPPET_MAX_LEN = 200
_SNAPSHOT_MAX_ITEMS = 10
_SEMANTIC_TOP_K = 5

_executor = ThreadPoolExecutor(max_workers=4)


def _do_semantic_search(agent_id: str, query: str, source: str) -> list[dict]:
    """Run a synchronous semantic search against Qdrant.

    Deduplication uses the provider's ``dedup_key`` so each integration
    deduplicates by its own item identity field.
    """
    try:
        provider = get_provider(source)
        dedup_field = provider.dedup_key if provider else "message_id"

        query_vector = embed_service.embed_single(query)
        raw = qdrant_service.search(
            agent_id=agent_id,
            query_vector=query_vector,
            source=source,
            top_k=_SEMANTIC_TOP_K * 3,
        )
        # Deduplicate by provider's dedup key — keep highest score
        seen: dict[str, dict] = {}
        for r in raw:
            item_id = r.get(dedup_field)
            if not isinstance(item_id, str):
                continue
            if item_id not in seen or r["score"] > seen[item_id]["score"]:
                seen[item_id] = r
        return sorted(seen.values(), key=lambda x: x["score"], reverse=True)[
            :_SEMANTIC_TOP_K
        ]
    except Exception:
        logger.exception("Semantic search failed for agent %s", agent_id)
        return []


def _do_snapshot(agent_id: str, source: str) -> list[dict]:
    """Run a synchronous snapshot query for the given source via its provider."""
    try:
        provider = get_provider(source)
        if not provider:
            return []
        return provider.snapshot(agent_id, hours=provider.default_snapshot_hours)
    except Exception:
        logger.exception("Snapshot failed for agent %s (source=%s)", agent_id, source)
        return []


async def build_context_block(
    db: Session,
    agent_id: str,
    user_message: str,
) -> str | None:
    """Build the injected context block for an agent's chat request.

    Returns None if the agent has no completed third-party contexts.
    """
    assign_repo = ThirdPartyContextAssignmentRepository(db)
    contexts = assign_repo.get_contexts_for_agent(agent_id, status="complete")
    if not contexts:
        return None

    # Collect source types from completed contexts
    sources: list[str] = []
    seen_sources: set[str] = set()
    for ctx in contexts:
        src = str(ctx.integration_name)
        if src not in seen_sources:
            seen_sources.add(src)
            sources.append(src)

    # Run semantic search + snapshot in parallel for each source
    loop = asyncio.get_running_loop()
    futures = []
    for source in sources:
        futures.append(
            loop.run_in_executor(
                _executor, _do_semantic_search, agent_id, user_message, source
            )
        )
        futures.append(
            loop.run_in_executor(_executor, _do_snapshot, agent_id, source)
        )

    results = await asyncio.gather(*futures, return_exceptions=True)

    # results come in pairs per source: [semantic_0, snapshot_0, semantic_1, snapshot_1, ...]
    source_data: dict[str, dict[str, list[dict]]] = {}
    for idx, res in enumerate(results):
        if isinstance(res, BaseException):
            logger.warning("Context sub-query failed: %s", res)
            continue
        source_idx = idx // 2
        source_name = sources[source_idx]
        if source_name not in source_data:
            source_data[source_name] = {"semantic": [], "snapshot": []}
        if idx % 2 == 0:
            source_data[source_name]["semantic"].extend(res)  # type: ignore[arg-type]
        else:
            source_data[source_name]["snapshot"].extend(res)  # type: ignore[arg-type]

    if not source_data:
        return None

    has_data = any(
        d["semantic"] or d["snapshot"]
        for d in source_data.values()
    )
    if not has_data:
        return None

    # Assemble the block — each source renders through its provider
    # Build the list of active source display names for the preamble
    active_sources = [
        get_provider(s).display_name
        for s in sources
        if s in source_data
        and (source_data[s]["semantic"] or source_data[s]["snapshot"])
        and get_provider(s)
    ]

    parts: list[str] = [
        "[THIRD-PARTY ACCOUNT CONTEXT]",
        "The following is contextual data retrieved from the user's own connected accounts.",
        "This is NOT a group chat — it is private data from their linked integrations "
        f"({', '.join(active_sources)}) provided to help you answer their questions.",
        "Use this context when relevant. Do not present it as group chat or shared conversation.",
        "",
    ]

    for source_name in sources:
        if source_name not in source_data:
            continue
        data = source_data[source_name]
        if not data["semantic"] and not data["snapshot"]:
            continue

        provider = get_provider(source_name)
        if not provider:
            continue

        if parts:
            parts.append("")

        parts.append(provider.context_block_header())

        snapshot_lines = provider.format_snapshot_lines(data["snapshot"], max_items=_SNAPSHOT_MAX_ITEMS)
        if snapshot_lines:
            parts.append(provider.snapshot_label())
            parts.extend(snapshot_lines)

        semantic_lines = provider.format_semantic_lines(
            data["semantic"], max_items=_SEMANTIC_TOP_K, snippet_max_len=_SNIPPET_MAX_LEN,
        )
        if semantic_lines:
            if snapshot_lines:
                parts.append("")
            parts.append(provider.semantic_label())
            parts.extend(semantic_lines)

        parts.append(provider.context_block_footer())

    if not parts:
        return None

    block = "\n".join(parts)

    # Truncate to stay within token budget
    if len(block) > _MAX_CONTEXT_CHARS:
        block = block[:_MAX_CONTEXT_CHARS] + "\n--------------------"

    return block
