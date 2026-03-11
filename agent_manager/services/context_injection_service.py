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
from ..services.gmail_search_service import snapshot as gmail_snapshot

logger = logging.getLogger(__name__)

# Hard cap on injected context to control token cost.
_MAX_CONTEXT_CHARS = 4000  # ~1000 tokens at ~4 chars/token
_SNIPPET_MAX_LEN = 200
_SNAPSHOT_MAX_ITEMS = 10
_SEMANTIC_TOP_K = 5

_executor = ThreadPoolExecutor(max_workers=4)


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _build_snapshot_lines(snapshot_results: list[dict]) -> list[str]:
    """Format snapshot results as compact one-liner summaries."""
    lines: list[str] = []
    for item in snapshot_results[:_SNAPSHOT_MAX_ITEMS]:
        date = item.get("date", "")
        sender = item.get("from", "")
        subject = item.get("subject", "")
        lines.append(f"• [{date}] From: {sender} | Subject: {subject}")
    return lines


def _build_semantic_lines(search_results: list[dict]) -> list[str]:
    """Format semantic search results with truncated snippets."""
    lines: list[str] = []
    for i, item in enumerate(search_results[:_SEMANTIC_TOP_K], 1):
        sender = item.get("from", "")
        date = item.get("date", "")
        subject = item.get("subject", "")
        snippet = _truncate(item.get("snippet", ""), _SNIPPET_MAX_LEN)
        lines.append(
            f"{i}. From: {sender} | Date: {date} | Subject: {subject}\n"
            f"   {snippet}"
        )
    return lines


def _do_semantic_search(agent_id: str, query: str, source: str) -> list[dict]:
    """Run a synchronous semantic search against Qdrant."""
    try:
        query_vector = embed_service.embed_single(query)
        raw = qdrant_service.search(
            agent_id=agent_id,
            query_vector=query_vector,
            source=source,
            top_k=_SEMANTIC_TOP_K * 3,
        )
        # Deduplicate by message_id — keep highest score
        seen: dict[str, dict] = {}
        for r in raw:
            mid = r.get("message_id")
            if not isinstance(mid, str):
                continue
            if mid not in seen or r["score"] > seen[mid]["score"]:
                seen[mid] = r
        return sorted(seen.values(), key=lambda x: x["score"], reverse=True)[
            :_SEMANTIC_TOP_K
        ]
    except Exception:
        logger.exception("Semantic search failed for agent %s", agent_id)
        return []


def _do_snapshot(agent_id: str, hours: int = 24) -> list[dict]:
    """Run a synchronous snapshot query."""
    try:
        return gmail_snapshot(agent_id, hours=hours)
    except Exception:
        logger.exception("Snapshot failed for agent %s", agent_id)
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
    sources: set[str] = set()
    for ctx in contexts:
        sources.add(str(ctx.integration_name))

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
            loop.run_in_executor(_executor, _do_snapshot, agent_id, 24)
        )

    results = await asyncio.gather(*futures, return_exceptions=True)

    # results come in pairs: [semantic_0, snapshot_0, semantic_1, snapshot_1, ...]
    all_semantic: list[dict] = []
    all_snapshot: list[dict] = []
    for idx, res in enumerate(results):
        if isinstance(res, BaseException):
            logger.warning("Context sub-query failed: %s", res)
            continue
        if idx % 2 == 0:
            all_semantic.extend(res)  # type: ignore[arg-type]
        else:
            all_snapshot.extend(res)  # type: ignore[arg-type]

    if not all_semantic and not all_snapshot:
        return None

    # Assemble the block
    parts: list[str] = ["--- Email Context ---"]

    snapshot_lines = _build_snapshot_lines(all_snapshot)
    if snapshot_lines:
        parts.append("Recent activity (last 24h):")
        parts.extend(snapshot_lines)

    semantic_lines = _build_semantic_lines(all_semantic)
    if semantic_lines:
        if snapshot_lines:
            parts.append("")
        parts.append("Relevant emails for your query:")
        parts.extend(semantic_lines)

    parts.append("--------------------")

    block = "\n".join(parts)

    # Truncate to stay within token budget
    if len(block) > _MAX_CONTEXT_CHARS:
        block = block[:_MAX_CONTEXT_CHARS] + "\n--------------------"

    return block
