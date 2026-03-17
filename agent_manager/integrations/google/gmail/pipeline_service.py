"""Digest → chunk → embed → upsert pipeline for Gmail messages."""
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
    """Clean a pre-parsed stored email dict down to what's useful for semantic search.

    S3 objects already contain only the fields we need — this step just cleans
    the body text (strip quotes, signatures, excessive whitespace) and enforces
    the hard character cap.
    """
    body = stored.get("body") or ""

    # Strip quoted reply lines (lines starting with >)
    lines = [l for l in body.splitlines() if not l.strip().startswith(">")]
    body = "\n".join(lines).strip()

    # Strip common signature markers
    for marker in ["\n-- \n", "\nSent from my", "\nGet Outlook", "\n--\n"]:
        if marker in body:
            body = body[:body.index(marker)].strip()

    # Strip excessive whitespace
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    return {
        "message_id": stored["id"],
        "thread_id": stored.get("threadId", ""),
        "subject": stored.get("subject") or "",
        "from": stored.get("from") or "",
        "to": stored.get("to") or "",
        "date": stored.get("date") or "",
        "snippet": stored.get("snippet") or "",
        "body": body[:8000],  # hard cap
        "has_attachment": stored.get("has_attachment", False),
        "label_ids": stored.get("labelIds") or [],
    }

# ── Chunk ────────────────────────────────────────────────────────────────────

def _chunk(digested: dict) -> list[dict]:
    """Split email body into overlapping word chunks."""
    words = (digested["body"] or "").split()

    if not words:
        # No body — index subject + snippet as a single chunk
        return [{
            **digested,
            "chunk_text": f"Subject: {digested['subject']}\n{digested['snippet']}".strip(),
            "chunk_index": 0,
            "total_chunks": 1,
        }]

    chunks: list[dict] = []
    start = 0
    while start < len(words):
        chunk_words = words[start:start + CHUNK_SIZE]
        # Prepend subject + sender to every chunk for retrieval relevance
        chunk_text = (
            f"Subject: {digested['subject']}\n"
            f"From: {digested['from']}\n\n"
            + " ".join(chunk_words)
        )
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
            f"{agent_id}:{chunk['message_id']}:{chunk['chunk_index']}",
        ))
        points.append(PointStruct(
            id=point_id,
            vector=vector,
            payload={
                # Isolation
                "agent_id": agent_id,
                "account_email": account_email,
                "source": "gmail",
                # Identity
                "message_id": chunk["message_id"],
                "thread_id": chunk["thread_id"],
                "chunk_index": chunk["chunk_index"],
                "total_chunks": chunk["total_chunks"],
                # Retrieval metadata
                "subject": chunk["subject"],
                "from": chunk["from"],
                "to": chunk["to"],
                "date": chunk["date"],
                "snippet": chunk["snippet"],
                "has_attachment": chunk["has_attachment"],
                "label_ids": chunk["label_ids"],
                # S3 pointer
                "s3_key": s3_service.gmail_raw_key(agent_id, chunk["message_id"]),
            },
        ))

    qdrant_service.upsert_points(points)

# ── Public API ───────────────────────────────────────────────────────────────

def build_chunks(stored_messages: list[dict]) -> list[dict]:
    """Digest and chunk a list of pre-parsed stored email dicts.

    S3 objects are already parsed; this step only cleans the body and chunks.

    Args:
        stored_messages: Clean email dicts as stored in S3 (already parsed).

    Returns:
        Flat list of chunk dicts with ``chunk_text`` and metadata fields.
    """
    all_chunks: list[dict] = []
    for stored in stored_messages:
        digested = _digest(stored)
        all_chunks.extend(_chunk(digested))
    return all_chunks


def process_messages_batch(
    stored_messages: list[dict], agent_id: str, account_email: str
) -> None:
    """Process a batch of emails in one embed call and one Qdrant upsert.

    Digests and chunks all messages, embeds all chunks in a single API call,
    then upserts all resulting points in one go.

    Args:
        stored_messages: Pre-parsed email dicts loaded from S3.
        agent_id: Agent whose mailbox the messages belong to.
        account_email: Gmail address for payload metadata.
    """
    all_chunks = build_chunks(stored_messages)
    if not all_chunks:
        return

    texts = [c["chunk_text"] for c in all_chunks]
    vectors = embed_service.embed_texts_safe(texts)

    points = []
    for chunk, vector in zip(all_chunks, vectors):
        point_id = str(uuid.uuid5(
            uuid.NAMESPACE_DNS,
            f"{agent_id}:{chunk['message_id']}:{chunk['chunk_index']}",
        ))
        points.append(PointStruct(
            id=point_id,
            vector=vector,
            payload={
                "agent_id": agent_id,
                "account_email": account_email,
                "source": "gmail",
                "message_id": chunk["message_id"],
                "thread_id": chunk["thread_id"],
                "chunk_index": chunk["chunk_index"],
                "total_chunks": chunk["total_chunks"],
                "subject": chunk["subject"],
                "from": chunk["from"],
                "to": chunk["to"],
                "date": chunk["date"],
                "snippet": chunk["snippet"],
                "has_attachment": chunk["has_attachment"],
                "label_ids": chunk["label_ids"],
                "s3_key": s3_service.gmail_raw_key(agent_id, chunk["message_id"]),
            },
        ))

    qdrant_service.upsert_points(points)


def process_message(stored: dict, agent_id: str, account_email: str) -> None:
    """Full pipeline for a single pre-parsed email dict loaded from S3."""
    digested = _digest(stored)
    chunks = _chunk(digested)
    _embed_and_upsert(chunks, agent_id, account_email)