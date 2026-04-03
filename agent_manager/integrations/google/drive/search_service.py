"""Semantic search over Google Drive file embeddings in Qdrant."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agent_manager.services import embed_service, qdrant_service


def search_files(
    agent_id: str,
    query: str,
    top_k: int = 10,
) -> list[dict]:
    """Search Drive files semantically. Returns deduplicated, ranked results."""
    query_vector = embed_service.embed_single(query)

    raw_results = qdrant_service.search(
        agent_id=agent_id,
        query_vector=query_vector,
        source="google_drive",
        top_k=top_k * 3,
    )

    # Deduplicate by file_id — keep highest-scoring chunk per file
    seen: dict[str, dict] = {}
    for r in raw_results:
        fid = r.get("file_id")
        if not isinstance(fid, str):
            continue
        if fid not in seen or r["score"] > seen[fid]["score"]:
            seen[fid] = r

    results = sorted(seen.values(), key=lambda x: x["score"], reverse=True)[:top_k]

    return [
        {
            "file_id": r["file_id"],
            "title": r.get("title", ""),
            "owner": r.get("owner", ""),
            "mime_type": r.get("mime_type", ""),
            "snippet": r.get("snippet", ""),
            "modified_time": r.get("modified_time", ""),
            "web_view_link": r.get("web_view_link", ""),
            "shared": r.get("shared", False),
            "size": r.get("size", ""),
            "has_content": r.get("has_content", False),
            "relevance_score": round(r["score"], 3),
            "s3_key": r.get("s3_key"),
        }
        for r in results
    ]


def _parse_datetime(value: str) -> datetime | None:
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
    """Return recently modified Drive files for session context."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    results = search_files(agent_id, "recently modified files", top_k=50)
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

    # Fallback: scan Qdrant payloads
    payloads = qdrant_service.list_payloads_for_agent_source(
        agent_id=agent_id,
        source="google_drive",
        limit=5000,
    )

    by_file: dict[str, dict] = {}
    for payload in payloads:
        file_id = payload.get("file_id")
        mod_value = payload.get("modified_time")
        if not isinstance(file_id, str) or not isinstance(mod_value, str):
            continue
        dt = _parse_datetime(mod_value)
        if not dt or dt < cutoff:
            continue
        current = by_file.get(file_id)
        if not current:
            by_file[file_id] = {**payload, "_parsed_dt": dt}
        elif isinstance(current.get("_parsed_dt"), datetime) and dt > current["_parsed_dt"]:
            by_file[file_id] = {**payload, "_parsed_dt": dt}

    ordered = sorted(by_file.values(), key=lambda item: item["_parsed_dt"], reverse=True)[:50]

    return [
        {
            "file_id": item.get("file_id", ""),
            "title": item.get("title", ""),
            "owner": item.get("owner", ""),
            "mime_type": item.get("mime_type", ""),
            "snippet": item.get("snippet", ""),
            "modified_time": item.get("modified_time", ""),
            "web_view_link": item.get("web_view_link", ""),
            "shared": item.get("shared", False),
            "size": item.get("size", ""),
            "has_content": item.get("has_content", False),
            "relevance_score": 0.0,
            "s3_key": item.get("s3_key"),
        }
        for item in ordered
    ]
