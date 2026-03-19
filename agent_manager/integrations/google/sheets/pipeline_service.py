"""Digest → chunk → embed → upsert pipeline for Google Sheets."""
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
    """Clean a stored sheet dict for semantic search."""
    content = stored.get("content") or ""
    content = re.sub(r"\n{3,}", "\n\n", content).strip()

    # Build a snippet from the first ~300 chars for display in search results
    snippet = content[:300].strip()
    if len(content) > 300:
        snippet += "…"

    return {
        "sheet_id": stored["id"],
        "title": stored.get("title") or "",
        "owner": stored.get("owner") or "",
        "content": content[:8000],
        "snippet": snippet,
        "modified_time": stored.get("modified_time") or "",
        "created_time": stored.get("created_time") or "",
        "web_view_link": stored.get("web_view_link") or "",
        "shared": stored.get("shared", False),
    }

# ── Chunk ────────────────────────────────────────────────────────────────────

def _chunk(digested: dict) -> list[dict]:
    """Split sheet content into overlapping word chunks."""
    header = f"Spreadsheet: {digested['title']}\nOwner: {digested['owner']}\n\n"
    words = (digested["content"] or "").split()

    if not words:
        return [{
            **digested,
            "chunk_text": f"Spreadsheet: {digested['title']} (empty spreadsheet)",
            "chunk_index": 0,
            "total_chunks": 1,
        }]

    chunks: list[dict] = []
    start = 0
    while start < len(words):
        chunk_words = words[start:start + CHUNK_SIZE]
        chunk_text = header + " ".join(chunk_words)
        chunks.append({
            **digested,
            "chunk_text": chunk_text,
            "chunk_index": len(chunks),
            "total_chunks": -1,
        })
        start += CHUNK_SIZE - CHUNK_OVERLAP
        if start >= len(words):
            break

    for c in chunks:
        c["total_chunks"] = len(chunks)

    return chunks

# ── Public API ───────────────────────────────────────────────────────────────

def build_chunks(stored_sheets: list[dict]) -> list[dict]:
    all_chunks: list[dict] = []
    for stored in stored_sheets:
        digested = _digest(stored)
        all_chunks.extend(_chunk(digested))
    return all_chunks


def process_sheets_batch(
    stored_sheets: list[dict], agent_id: str, account_email: str,
) -> None:
    all_chunks = build_chunks(stored_sheets)
    if not all_chunks:
        return

    texts = [c["chunk_text"] for c in all_chunks]
    vectors = embed_service.embed_texts_safe(texts)

    points = []
    for chunk, vector in zip(all_chunks, vectors):
        point_id = str(uuid.uuid5(
            uuid.NAMESPACE_DNS,
            f"{agent_id}:sheets:{chunk['sheet_id']}:{chunk['chunk_index']}",
        ))
        points.append(PointStruct(
            id=point_id,
            vector=vector,
            payload={
                "agent_id": agent_id,
                "account_email": account_email,
                "source": "google_sheets",
                "sheet_id": chunk["sheet_id"],
                "chunk_index": chunk["chunk_index"],
                "total_chunks": chunk["total_chunks"],
                "title": chunk["title"],
                "owner": chunk["owner"],
                "modified_time": chunk["modified_time"],
                "created_time": chunk["created_time"],
                "web_view_link": chunk["web_view_link"],
                "shared": chunk["shared"],
                "snippet": chunk.get("snippet", ""),
                "s3_key": s3_service.raw_key(agent_id, "sheets", chunk["sheet_id"]),
            },
        ))

    qdrant_service.upsert_points(points)


def process_sheet(stored: dict, agent_id: str, account_email: str) -> None:
    digested = _digest(stored)
    chunks = _chunk(digested)
    if not chunks:
        return

    texts = [c["chunk_text"] for c in chunks]
    vectors = embed_service.embed_texts(texts)

    points = []
    for chunk, vector in zip(chunks, vectors):
        point_id = str(uuid.uuid5(
            uuid.NAMESPACE_DNS,
            f"{agent_id}:sheets:{chunk['sheet_id']}:{chunk['chunk_index']}",
        ))
        points.append(PointStruct(
            id=point_id,
            vector=vector,
            payload={
                "agent_id": agent_id,
                "account_email": account_email,
                "source": "google_sheets",
                "sheet_id": chunk["sheet_id"],
                "chunk_index": chunk["chunk_index"],
                "total_chunks": chunk["total_chunks"],
                "title": chunk["title"],
                "owner": chunk["owner"],
                "modified_time": chunk["modified_time"],
                "created_time": chunk["created_time"],
                "web_view_link": chunk["web_view_link"],
                "shared": chunk["shared"],
                "snippet": chunk.get("snippet", ""),
                "s3_key": s3_service.raw_key(agent_id, "sheets", chunk["sheet_id"]),
            },
        ))

    qdrant_service.upsert_points(points)
