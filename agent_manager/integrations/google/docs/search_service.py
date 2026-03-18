"""Semantic search over Google Docs embeddings in Qdrant."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agent_manager.services import embed_service, qdrant_service


def search_docs(
    agent_id: str,
    query: str,
    top_k: int = 10,
) -> list[dict]:
    """Search docs semantically. Returns deduplicated, ranked results."""
    query_vector = embed_service.embed_single(query)

    raw_results = qdrant_service.search(
        agent_id=agent_id,
        query_vector=query_vector,
        source="google_docs",
        top_k=top_k * 3,
    )

    # Deduplicate by doc_id — keep highest-scoring chunk per doc
    seen: dict[str, dict] = {}
    for r in raw_results:
        did = r.get("doc_id")
        if not isinstance(did, str):
            continue
        if did not in seen or r["score"] > seen[did]["score"]:
            seen[did] = r

    results = sorted(seen.values(), key=lambda x: x["score"], reverse=True)[:top_k]

    return [
        {
            "doc_id": r["doc_id"],
            "title": r.get("title", ""),
            "owner": r.get("owner", ""),
            "snippet": r.get("snippet", ""),
            "modified_time": r.get("modified_time", ""),
            "web_view_link": r.get("web_view_link", ""),
            "shared": r.get("shared", False),
            "relevance_score": round(r["score"], 3),
            "s3_key": r.get("s3_key"),
        }
        for r in results
    ]


def _parse_datetime(value: str) -> datetime | None:
    """Parse an ISO 8601 datetime string to an aware UTC datetime."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def snapshot(agent_id: str, hours: int = 168) -> list[dict]:
    """Return recently modified docs for session context.

    Args:
        agent_id: Owning agent.
        hours: Look-back window in hours (default 7 days).

    Returns:
        Docs modified within the last *hours* hours.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Try semantic search first
    results = search_docs(agent_id, "recently modified documents", top_k=50)
    recent: list[dict] = []
    for result in results:
        mod_value = result.get("modified_time")
        if not isinstance(mod_value, str):
            continue
        dt = _parse_datetime(mod_value)
        if dt and dt >= cutoff:
            recent.append(result)

    if recent:
        return sorted(recent, key=lambda x: x["modified_time"], reverse=True)

    # Fallback: scan Qdrant payloads directly
    payloads = qdrant_service.list_payloads_for_agent_source(
        agent_id=agent_id,
        source="google_docs",
        limit=5000,
    )

    by_doc: dict[str, dict] = {}
    for payload in payloads:
        doc_id = payload.get("doc_id")
        mod_value = payload.get("modified_time")
        if not isinstance(doc_id, str) or not isinstance(mod_value, str):
            continue

        dt = _parse_datetime(mod_value)
        if not dt or dt < cutoff:
            continue

        current = by_doc.get(doc_id)
        if not current:
            by_doc[doc_id] = {**payload, "_parsed_dt": dt}
            continue

        current_dt = current.get("_parsed_dt")
        if isinstance(current_dt, datetime) and dt > current_dt:
            by_doc[doc_id] = {**payload, "_parsed_dt": dt}

    ordered = sorted(
        by_doc.values(),
        key=lambda item: item["_parsed_dt"],
        reverse=True,
    )[:50]

    return [
        {
            "doc_id": item.get("doc_id", ""),
            "title": item.get("title", ""),
            "owner": item.get("owner", ""),
            "snippet": item.get("snippet", ""),
            "modified_time": item.get("modified_time", ""),
            "web_view_link": item.get("web_view_link", ""),
            "shared": item.get("shared", False),
            "relevance_score": 0.0,
            "s3_key": item.get("s3_key"),
        }
        for item in ordered
    ]
