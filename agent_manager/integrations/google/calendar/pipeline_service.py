"""Digest → chunk → embed → upsert pipeline for Calendar events."""
from __future__ import annotations

import logging
import re
import uuid

from qdrant_client.models import PointStruct

from agent_manager.services import s3_service, embed_service, qdrant_service

logger = logging.getLogger(__name__)

CHUNK_SIZE = 500  # words per chunk
CHUNK_OVERLAP = 50  # word overlap between chunks

# ── Digest ───────────────────────────────────────────────────────────────────

def _digest(stored: dict) -> dict:
    """Clean a stored calendar event dict for semantic search."""
    description = stored.get("description") or ""

    # Strip excessive whitespace
    description = re.sub(r"\n{3,}", "\n\n", description).strip()

    attendees_raw = stored.get("attendees") or []
    attendees_str = ", ".join(
        a.get("email", a.get("displayName", ""))
        for a in attendees_raw
        if a.get("email") or a.get("displayName")
    )

    return {
        "event_id": stored["id"],
        "summary": stored.get("summary") or "",
        "description": description[:8000],  # hard cap
        "start": stored.get("start") or "",
        "end": stored.get("end") or "",
        "location": stored.get("location") or "",
        "organizer": stored.get("organizer") or "",
        "attendees": attendees_str,
        "status": stored.get("status") or "",
        "recurring_event_id": stored.get("recurringEventId") or "",
        "html_link": stored.get("htmlLink") or "",
        "created": stored.get("created") or "",
        "updated": stored.get("updated") or "",
    }

# ── Chunk ────────────────────────────────────────────────────────────────────

def _chunk(digested: dict) -> list[dict]:
    """Split event into overlapping word chunks."""
    # Build a rich text representation of the event
    parts = []
    if digested["summary"]:
        parts.append(f"Event: {digested['summary']}")
    if digested["start"]:
        parts.append(f"Start: {digested['start']}")
    if digested["end"]:
        parts.append(f"End: {digested['end']}")
    if digested["location"]:
        parts.append(f"Location: {digested['location']}")
    if digested["organizer"]:
        parts.append(f"Organizer: {digested['organizer']}")
    if digested["attendees"]:
        parts.append(f"Attendees: {digested['attendees']}")
    if digested["status"]:
        parts.append(f"Status: {digested['status']}")
    if digested["description"]:
        parts.append(f"\n{digested['description']}")

    full_text = "\n".join(parts)
    words = full_text.split()

    if not words:
        return [{
            **digested,
            "chunk_text": f"Event: {digested['summary']}",
            "chunk_index": 0,
            "total_chunks": 1,
        }]

    chunks: list[dict] = []
    start = 0
    while start < len(words):
        chunk_words = words[start:start + CHUNK_SIZE]
        chunk_text = " ".join(chunk_words)
        chunks.append({
            **digested,
            "chunk_text": chunk_text,
            "chunk_index": len(chunks),
            "total_chunks": -1,  # filled after loop
        })
        start += CHUNK_SIZE - CHUNK_OVERLAP
        if start >= len(words):
            break

    for c in chunks:
        c["total_chunks"] = len(chunks)

    return chunks

# ── Embed + Upsert ───────────────────────────────────────────────────────────

def _embed_and_upsert(chunks: list[dict], agent_id: str, account_email: str):
    """Embed all chunks in one API call and upsert to Qdrant."""
    if not chunks:
        return

    texts = [c["chunk_text"] for c in chunks]
    vectors = embed_service.embed_texts(texts)

    points = []
    for chunk, vector in zip(chunks, vectors):
        point_id = str(uuid.uuid5(
            uuid.NAMESPACE_DNS,
            f"{agent_id}:calendar:{chunk['event_id']}:{chunk['chunk_index']}",
        ))
        points.append(PointStruct(
            id=point_id,
            vector=vector,
            payload={
                "agent_id": agent_id,
                "account_email": account_email,
                "source": "google_calendar",
                "event_id": chunk["event_id"],
                "chunk_index": chunk["chunk_index"],
                "total_chunks": chunk["total_chunks"],
                "summary": chunk["summary"],
                "start": chunk["start"],
                "end": chunk["end"],
                "location": chunk["location"],
                "organizer": chunk["organizer"],
                "attendees": chunk["attendees"],
                "status": chunk["status"],
                "recurring_event_id": chunk["recurring_event_id"],
                "html_link": chunk["html_link"],
                "created": chunk["created"],
                "updated": chunk["updated"],
                "s3_key": s3_service.calendar_raw_key(agent_id, chunk["event_id"]),
            },
        ))

    qdrant_service.upsert_points(points)

# ── Public API ───────────────────────────────────────────────────────────────

def build_chunks(stored_events: list[dict]) -> list[dict]:
    """Digest and chunk a list of pre-parsed stored event dicts."""
    all_chunks: list[dict] = []
    for stored in stored_events:
        digested = _digest(stored)
        all_chunks.extend(_chunk(digested))
    return all_chunks


def process_events_batch(
    stored_events: list[dict], agent_id: str, account_email: str
) -> None:
    """Process a batch of events in one embed call and one Qdrant upsert."""
    all_chunks = build_chunks(stored_events)
    if not all_chunks:
        return

    texts = [c["chunk_text"] for c in all_chunks]
    vectors = embed_service.embed_texts_safe(texts)

    points = []
    for chunk, vector in zip(all_chunks, vectors):
        point_id = str(uuid.uuid5(
            uuid.NAMESPACE_DNS,
            f"{agent_id}:calendar:{chunk['event_id']}:{chunk['chunk_index']}",
        ))
        points.append(PointStruct(
            id=point_id,
            vector=vector,
            payload={
                "agent_id": agent_id,
                "account_email": account_email,
                "source": "google_calendar",
                "event_id": chunk["event_id"],
                "chunk_index": chunk["chunk_index"],
                "total_chunks": chunk["total_chunks"],
                "summary": chunk["summary"],
                "start": chunk["start"],
                "end": chunk["end"],
                "location": chunk["location"],
                "organizer": chunk["organizer"],
                "attendees": chunk["attendees"],
                "status": chunk["status"],
                "recurring_event_id": chunk["recurring_event_id"],
                "html_link": chunk["html_link"],
                "created": chunk["created"],
                "updated": chunk["updated"],
                "s3_key": s3_service.calendar_raw_key(agent_id, chunk["event_id"]),
            },
        ))

    qdrant_service.upsert_points(points)


def process_event(stored: dict, agent_id: str, account_email: str) -> None:
    """Full pipeline for a single pre-parsed event dict loaded from S3."""
    digested = _digest(stored)
    chunks = _chunk(digested)
    _embed_and_upsert(chunks, agent_id, account_email)
