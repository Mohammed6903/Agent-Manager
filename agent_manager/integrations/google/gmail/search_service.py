"""Semantic search over Gmail embeddings in Qdrant."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from agent_manager.services import embed_service, qdrant_service, s3_service


def search_emails(
    agent_id: str,
    query: str,
    top_k: int = 10,
    only_unread: bool = False,
    has_attachment: bool = False,
) -> list[dict]:
    """Search emails semantically. Returns deduplicated, ranked results.

    Args:
        agent_id: Agent whose embeddings to search.
        query: Natural language query string.
        top_k: Maximum number of results to return.
        only_unread: When True, exclude messages without the UNREAD label.
        has_attachment: When True, exclude messages with no attachments.

    Returns:
        List of result dicts sorted by descending relevance score.
    """
    query_vector = embed_service.embed_single(query)

    # Over-fetch so deduplication still yields top_k unique messages
    raw_results = qdrant_service.search(
        agent_id=agent_id,
        query_vector=query_vector,
        source="gmail",
        top_k=top_k * 3,
    )

    # Deduplicate by message_id — keep highest-scoring chunk per message
    seen: dict[str, dict] = {}
    for r in raw_results:
        mid = r.get("message_id")
        if not isinstance(mid, str):
            continue
        if mid not in seen or r["score"] > seen[mid]["score"]:
            seen[mid] = r

    results = list(seen.values())

    if only_unread:
        results = [r for r in results if "UNREAD" in r.get("label_ids", [])]
    if has_attachment:
        results = [r for r in results if r.get("has_attachment")]

    results = sorted(results, key=lambda x: x["score"], reverse=True)[:top_k]

    return [
        {
            "message_id": r["message_id"],
            "thread_id": r["thread_id"],
            "subject": r["subject"],
            "from": r["from"],
            "to": r["to"],
            "date": r["date"],
            "snippet": r["snippet"],
            "has_attachment": r["has_attachment"],
            "label_ids": r["label_ids"],
            "relevance_score": round(r["score"], 3),
            "s3_key": r.get("s3_key"),
        }
        for r in results
    ]


def get_full_email(agent_id: str, message_id: str) -> dict | None:
    """Fetch full raw email from S3 by message_id.

    Args:
        agent_id: Owning agent.
        message_id: Gmail message ID.

    Returns:
        Parsed message dict, or None if not found in S3.
    """
    raw = s3_service.load_gmail_raw(agent_id, message_id)
    if not raw:
        return None
    from agent_manager.integrations.google.gmail.service import _parse_message  # noqa: PLC0415

    return _parse_message(raw)


def _parse_email_date(value: str) -> datetime | None:
    """Parse an RFC2822-like date header to an aware UTC datetime."""
    try:
        dt = parsedate_to_datetime(value)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def snapshot(agent_id: str, hours: int = 24) -> list[dict]:
    """Return a lightweight summary of recent emails for session context.

    Args:
        agent_id: Owning agent.
        hours: Look-back window in hours.

    Returns:
        Emails received within the last *hours* hours.

    Notes:
        First tries semantic retrieval. If no recent results are found, falls
        back to a recency-based scan from Qdrant payloads.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    results = search_emails(agent_id, "inbox recent emails", top_k=50)
    recent: list[dict] = []
    for result in results:
        date_value = result.get("date")
        if not isinstance(date_value, str):
            continue
        dt = _parse_email_date(date_value)
        if dt and dt >= cutoff:
            recent.append(result)

    if recent:
        return recent

    payloads = qdrant_service.list_payloads_for_agent_source(
        agent_id=agent_id,
        source="gmail",
        limit=5000,
    )

    by_message: dict[str, dict] = {}
    for payload in payloads:
        message_id = payload.get("message_id")
        date_value = payload.get("date")
        if not isinstance(message_id, str) or not isinstance(date_value, str):
            continue

        dt = _parse_email_date(date_value)
        if not dt or dt < cutoff:
            continue

        current = by_message.get(message_id)
        if not current:
            by_message[message_id] = {**payload, "_parsed_dt": dt}
            continue

        current_dt = current.get("_parsed_dt")
        if isinstance(current_dt, datetime) and dt > current_dt:
            by_message[message_id] = {**payload, "_parsed_dt": dt}

    ordered = sorted(
        by_message.values(),
        key=lambda item: item["_parsed_dt"],
        reverse=True,
    )[:50]

    return [
        {
            "message_id": item.get("message_id", ""),
            "thread_id": item.get("thread_id", ""),
            "subject": item.get("subject", ""),
            "from": item.get("from", ""),
            "to": item.get("to", ""),
            "date": item.get("date", ""),
            "snippet": item.get("snippet", ""),
            "has_attachment": bool(item.get("has_attachment", False)),
            "label_ids": item.get("label_ids", []),
            "relevance_score": 0.0,
            "s3_key": item.get("s3_key"),
        }
        for item in ordered
    ]
