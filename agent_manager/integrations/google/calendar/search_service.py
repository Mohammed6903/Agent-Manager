"""Semantic search over Calendar embeddings in Qdrant."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agent_manager.services import embed_service, qdrant_service, s3_service


def search_events(
    agent_id: str,
    query: str,
    top_k: int = 10,
) -> list[dict]:
    """Search calendar events semantically. Returns deduplicated, ranked results."""
    query_vector = embed_service.embed_single(query)

    raw_results = qdrant_service.search(
        agent_id=agent_id,
        query_vector=query_vector,
        source="google_calendar",
        top_k=top_k * 3,
    )

    # Deduplicate by event_id — keep highest-scoring chunk per event
    seen: dict[str, dict] = {}
    for r in raw_results:
        eid = r.get("event_id")
        if not isinstance(eid, str):
            continue
        if eid not in seen or r["score"] > seen[eid]["score"]:
            seen[eid] = r

    results = sorted(seen.values(), key=lambda x: x["score"], reverse=True)[:top_k]

    return [
        {
            "event_id": r["event_id"],
            "summary": r.get("summary", ""),
            "start": r.get("start", ""),
            "end": r.get("end", ""),
            "location": r.get("location", ""),
            "organizer": r.get("organizer", ""),
            "attendees": r.get("attendees", ""),
            "status": r.get("status", ""),
            "relevance_score": round(r["score"], 3),
            "s3_key": r.get("s3_key"),
        }
        for r in results
    ]


def _parse_event_datetime(value: str) -> datetime | None:
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
    """Return a lightweight summary of upcoming events for session context.

    Args:
        agent_id: Owning agent.
        hours: Look-ahead window in hours (default 7 days).

    Returns:
        Events within the next *hours* hours.
    """
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours)

    results = search_events(agent_id, "upcoming calendar events meetings", top_k=50)
    upcoming: list[dict] = []
    for result in results:
        start_value = result.get("start")
        if not isinstance(start_value, str):
            continue
        dt = _parse_event_datetime(start_value)
        if dt and now <= dt <= cutoff:
            upcoming.append(result)

    if upcoming:
        return sorted(upcoming, key=lambda x: x["start"])

    # Fallback: scan Qdrant payloads directly
    payloads = qdrant_service.list_payloads_for_agent_source(
        agent_id=agent_id,
        source="google_calendar",
        limit=5000,
    )

    by_event: dict[str, dict] = {}
    for payload in payloads:
        event_id = payload.get("event_id")
        start_value = payload.get("start")
        if not isinstance(event_id, str) or not isinstance(start_value, str):
            continue

        dt = _parse_event_datetime(start_value)
        if not dt or not (now <= dt <= cutoff):
            continue

        current = by_event.get(event_id)
        if not current:
            by_event[event_id] = {**payload, "_parsed_dt": dt}
            continue

        current_dt = current.get("_parsed_dt")
        if isinstance(current_dt, datetime) and dt < current_dt:
            by_event[event_id] = {**payload, "_parsed_dt": dt}

    ordered = sorted(
        by_event.values(),
        key=lambda item: item["_parsed_dt"],
    )[:50]

    return [
        {
            "event_id": item.get("event_id", ""),
            "summary": item.get("summary", ""),
            "start": item.get("start", ""),
            "end": item.get("end", ""),
            "location": item.get("location", ""),
            "organizer": item.get("organizer", ""),
            "attendees": item.get("attendees", ""),
            "status": item.get("status", ""),
            "relevance_score": 0.0,
            "s3_key": item.get("s3_key"),
        }
        for item in ordered
    ]
