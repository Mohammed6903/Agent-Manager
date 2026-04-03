"""Digest → chunk → embed → upsert pipeline for Google Drive files."""
from __future__ import annotations

import logging
import re
import uuid

from qdrant_client.models import PointStruct

from agent_manager.services import s3_service, embed_service, qdrant_service

logger = logging.getLogger(__name__)

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def _digest(stored: dict) -> dict:
    """Clean a stored file dict for semantic search."""
    content = stored.get("content") or ""
    has_content = stored.get("has_content", bool(content))

    if content:
        content = re.sub(r"\n{3,}", "\n\n", content).strip()

    snippet = ""
    if content:
        snippet = content[:300].strip()
        if len(content) > 300:
            snippet += "…"

    return {
        "file_id": stored["id"],
        "title": stored.get("title") or "",
        "owner": stored.get("owner") or "",
        "content": content[:8000] if content else "",
        "snippet": snippet,
        "mime_type": stored.get("mime_type") or "",
        "modified_time": stored.get("modified_time") or "",
        "created_time": stored.get("created_time") or "",
        "web_view_link": stored.get("web_view_link") or "",
        "shared": stored.get("shared", False),
        "size": stored.get("size", ""),
        "file_extension": stored.get("file_extension", ""),
        "has_content": has_content,
    }


def _chunk(digested: dict) -> list[dict]:
    """Split file content into overlapping word chunks.

    For metadata-only files (no content), creates a single chunk with
    file metadata for embedding.
    """
    title = digested["title"]
    owner = digested["owner"]
    mime = digested["mime_type"]
    content = digested["content"]

    if not content:
        # Metadata-only chunk for binary files
        meta_text = (
            f"File: {title}\n"
            f"Type: {mime}\n"
            f"Owner: {owner}\n"
            f"Modified: {digested['modified_time']}\n"
            f"Size: {digested['size']} bytes"
        )
        return [{
            **digested,
            "chunk_text": meta_text,
            "chunk_index": 0,
            "total_chunks": 1,
        }]

    header = f"File: {title}\nType: {mime}\nOwner: {owner}\n\n"
    words = content.split()

    if not words:
        return [{
            **digested,
            "chunk_text": f"File: {title} (empty)",
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


def build_chunks(stored_files: list[dict]) -> list[dict]:
    all_chunks: list[dict] = []
    for stored in stored_files:
        digested = _digest(stored)
        all_chunks.extend(_chunk(digested))
    return all_chunks


def process_drive_batch(
    stored_files: list[dict], agent_id: str, account_email: str,
) -> None:
    """Process a batch of files in one embed call and one Qdrant upsert."""
    all_chunks = build_chunks(stored_files)
    if not all_chunks:
        return

    texts = [c["chunk_text"] for c in all_chunks]
    vectors = embed_service.embed_texts_safe(texts)

    points = []
    for chunk, vector in zip(all_chunks, vectors):
        point_id = str(uuid.uuid5(
            uuid.NAMESPACE_DNS,
            f"{agent_id}:drive:{chunk['file_id']}:{chunk['chunk_index']}",
        ))
        points.append(PointStruct(
            id=point_id,
            vector=vector,
            payload={
                "agent_id": agent_id,
                "account_email": account_email,
                "source": "google_drive",
                "file_id": chunk["file_id"],
                "chunk_index": chunk["chunk_index"],
                "total_chunks": chunk["total_chunks"],
                "title": chunk["title"],
                "owner": chunk["owner"],
                "mime_type": chunk["mime_type"],
                "modified_time": chunk["modified_time"],
                "created_time": chunk["created_time"],
                "web_view_link": chunk["web_view_link"],
                "shared": chunk["shared"],
                "size": chunk["size"],
                "has_content": chunk["has_content"],
                "snippet": chunk.get("snippet", ""),
                "s3_key": s3_service.raw_key(agent_id, "drive", chunk["file_id"]),
            },
        ))

    qdrant_service.upsert_points(points)


def process_drive_file(stored: dict, agent_id: str, account_email: str) -> None:
    """Full pipeline for a single file."""
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
            f"{agent_id}:drive:{chunk['file_id']}:{chunk['chunk_index']}",
        ))
        points.append(PointStruct(
            id=point_id,
            vector=vector,
            payload={
                "agent_id": agent_id,
                "account_email": account_email,
                "source": "google_drive",
                "file_id": chunk["file_id"],
                "chunk_index": chunk["chunk_index"],
                "total_chunks": chunk["total_chunks"],
                "title": chunk["title"],
                "owner": chunk["owner"],
                "mime_type": chunk["mime_type"],
                "modified_time": chunk["modified_time"],
                "created_time": chunk["created_time"],
                "web_view_link": chunk["web_view_link"],
                "shared": chunk["shared"],
                "size": chunk["size"],
                "has_content": chunk["has_content"],
                "snippet": chunk.get("snippet", ""),
                "s3_key": s3_service.raw_key(agent_id, "drive", chunk["file_id"]),
            },
        ))

    qdrant_service.upsert_points(points)
