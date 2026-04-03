"""Celery task helpers for Google Drive file ingestion → S3.

Indexes PDFs (text extraction), plain text files (.txt, .md, .csv, .json, .html),
and metadata-only for all other non-Doc/Sheet files (images, videos, binaries).

Explicitly SKIPS Google Docs and Sheets (handled by their own providers).
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import redis as redis_lib
from celery import current_task

from agent_manager.config import settings
from agent_manager.services import s3_service

logger = logging.getLogger(__name__)

# MIME types handled by dedicated providers — skip these
_SKIP_MIME_TYPES = {
    "application/vnd.google-apps.document",      # Google Docs
    "application/vnd.google-apps.spreadsheet",   # Google Sheets
    "application/vnd.google-apps.presentation",  # Google Slides (future)
}

# MIME types we can extract text from
_TEXT_EXPORTABLE_MIMES = {
    "application/pdf",
}

_PLAIN_TEXT_MIMES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "text/html",
    "application/json",
    "text/xml",
    "application/xml",
}

# Google-native types that can be exported as text (excluding Docs/Sheets/Slides)
_GOOGLE_EXPORT_MIMES = {
    "application/vnd.google-apps.drawing": "application/pdf",
}

_INTER_PAGE_DELAY: float = 0.5
_PAGE_SIZE = 100
_MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024  # 10 MB cap for text extraction

# ── Active-task Registry ──────────────────────────────────────────────────────

_ACTIVE_KEY = "openclaw:ingest:active"
_ACTIVE_TTL = 86_400


def _redis() -> redis_lib.Redis:
    return redis_lib.from_url(settings.REDIS_URL, decode_responses=True)


def _active_field(agent_id: str, task_type: str = "ingest") -> str:
    return f"google_drive:{task_type}:{agent_id}"


def register_active_task(agent_id: str, task_id: str, task_type: str = "ingest") -> None:
    r = _redis()
    r.hset(_ACTIVE_KEY, _active_field(agent_id, task_type=task_type), task_id)
    r.expire(_ACTIVE_KEY, _ACTIVE_TTL)


def unregister_active_task(agent_id: str, task_id: str, task_type: str = "ingest") -> None:
    field = _active_field(agent_id, task_type=task_type)
    r = _redis()
    current = r.hget(_ACTIVE_KEY, field)
    if current == task_id:
        r.hdel(_ACTIVE_KEY, field)


# ── Progress Helpers ─────────────────────────────────────────────────────────

def _update_progress(task_state: str, meta: dict[str, Any]) -> None:
    current_task.update_state(state=task_state, meta=meta)


# ── Content Extraction ───────────────────────────────────────────────────────

def _download_text_content(drive_service: Any, file_id: str, mime_type: str) -> str | None:
    """Download a file and return its text content, or None on failure."""
    try:
        response = drive_service.files().get_media(fileId=file_id).execute()
        if isinstance(response, bytes):
            if len(response) > _MAX_DOWNLOAD_BYTES:
                return response[:_MAX_DOWNLOAD_BYTES].decode("utf-8", errors="replace")
            return response.decode("utf-8", errors="replace")
        return str(response)
    except Exception:
        logger.warning("Failed to download file %s (mime=%s)", file_id, mime_type, exc_info=True)
        return None


def _extract_pdf_text(drive_service: Any, file_id: str) -> str | None:
    """Download a PDF and extract text. Uses simple byte decode as fallback."""
    try:
        response = drive_service.files().get_media(fileId=file_id).execute()
        if not isinstance(response, bytes):
            return None
        if len(response) > _MAX_DOWNLOAD_BYTES:
            return None

        # Try PyPDF2/pdfplumber if available, fall back to raw decode
        try:
            import io
            import pdfplumber
            with pdfplumber.open(io.BytesIO(response)) as pdf:
                pages = []
                for page in pdf.pages[:50]:  # cap at 50 pages
                    text = page.extract_text()
                    if text:
                        pages.append(text)
                return "\n\n".join(pages) if pages else None
        except ImportError:
            # pdfplumber not installed — try basic text extraction
            text = response.decode("utf-8", errors="replace")
            # Filter out binary garbage
            printable = "".join(c for c in text if c.isprintable() or c in "\n\r\t ")
            return printable.strip() if len(printable) > 100 else None
    except Exception:
        logger.warning("Failed to extract PDF text for %s", file_id, exc_info=True)
        return None


def _extract_content(drive_service: Any, file_meta: dict) -> str | None:
    """Extract text content from a file based on its MIME type."""
    mime_type = file_meta.get("mimeType", "")
    file_id = file_meta["id"]

    if mime_type in _PLAIN_TEXT_MIMES:
        return _download_text_content(drive_service, file_id, mime_type)

    if mime_type in _TEXT_EXPORTABLE_MIMES:
        return _extract_pdf_text(drive_service, file_id)

    if mime_type in _GOOGLE_EXPORT_MIMES:
        # Export Google-native types as PDF then extract text
        try:
            response = drive_service.files().export(
                fileId=file_id, mimeType="text/plain",
            ).execute()
            if isinstance(response, bytes):
                return response.decode("utf-8", errors="replace")
            return str(response)
        except Exception:
            return None

    # Non-extractable file — return None (metadata-only)
    return None


def _should_skip(mime_type: str) -> bool:
    """Return True if this file type is handled by a dedicated provider."""
    return mime_type in _SKIP_MIME_TYPES


def _parse_file(file_meta: dict, content: str | None) -> dict:
    """Build a clean dict for S3 storage."""
    owners = file_meta.get("owners", [])
    owner_email = owners[0].get("emailAddress", "") if owners else ""
    mime_type = file_meta.get("mimeType", "")

    return {
        "id": file_meta["id"],
        "title": file_meta.get("name", ""),
        "owner": owner_email,
        "content": content,  # None for binary/metadata-only files
        "mime_type": mime_type,
        "modified_time": file_meta.get("modifiedTime", ""),
        "created_time": file_meta.get("createdTime", ""),
        "web_view_link": file_meta.get("webViewLink", ""),
        "shared": file_meta.get("shared", False),
        "size": file_meta.get("size", ""),
        "file_extension": file_meta.get("fileExtension", ""),
        "has_content": content is not None and len(content or "") > 0,
    }


# ── Sync Strategies ───────────────────────────────────────────────────────────

def _full_sync(
    drive_service: Any,
    agent_id: str,
    counters: dict[str, int],
    is_aborted: Callable[[], bool],
) -> str | None:
    """Fetch ALL Drive files (excluding Docs/Sheets), extract text where possible, store in S3."""
    start_token_resp = drive_service.changes().getStartPageToken().execute()
    start_page_token: str = start_token_resp["startPageToken"]

    stored_ids = set(s3_service.list_item_ids(agent_id, "drive"))
    page_token: str | None = None

    while True:
        if is_aborted():
            return None

        kwargs: dict[str, Any] = {
            "q": "trashed=false",
            "pageSize": _PAGE_SIZE,
            "fields": "nextPageToken, files(id, name, mimeType, modifiedTime, createdTime, webViewLink, owners, shared, size, fileExtension)",
        }
        if page_token:
            kwargs["pageToken"] = page_token

        response = drive_service.files().list(**kwargs).execute()
        files = response.get("files", [])

        for file_meta in files:
            if is_aborted():
                return None

            file_id = file_meta.get("id")
            mime_type = file_meta.get("mimeType", "")

            if not file_id or _should_skip(mime_type):
                counters["skipped"] += 1
                continue

            if file_id in stored_ids:
                counters["skipped"] += 1
                continue

            content = _extract_content(drive_service, file_meta)
            parsed = _parse_file(file_meta, content)

            if s3_service.save_raw(agent_id, "drive", file_id, parsed):
                counters["fetched"] += 1
                stored_ids.add(file_id)
            else:
                counters["failed"] += 1

            total = counters["fetched"] + counters["skipped"] + counters["failed"]
            _update_progress(
                "FETCHING",
                {
                    "stage": "fetching",
                    "message": f"Fetching files ({counters['fetched']} new, {counters['skipped']} skipped)...",
                    "current": counters["fetched"],
                    "total": total,
                    "percentage": 0,
                    "skipped": counters["skipped"],
                    "failed": counters["failed"],
                },
            )

        page_token = response.get("nextPageToken")
        if not page_token:
            break

        time.sleep(_INTER_PAGE_DELAY)

    return start_page_token


def _incremental_sync(
    drive_service: Any,
    agent_id: str,
    page_token: str,
    counters: dict[str, int],
    is_aborted: Callable[[], bool],
) -> str | None:
    """Fetch only files changed since last sync using Drive changes API."""
    new_start_page_token: str | None = None

    while True:
        if is_aborted():
            return None

        response = drive_service.changes().list(
            pageToken=page_token,
            spaces="drive",
            fields="nextPageToken, newStartPageToken, changes(fileId, removed, file(id, name, mimeType, modifiedTime, createdTime, webViewLink, owners, shared, trashed, size, fileExtension))",
            pageSize=_PAGE_SIZE,
        ).execute()

        changes = response.get("changes", [])

        for change in changes:
            if is_aborted():
                return None

            file_id = change.get("fileId")
            if not file_id:
                continue

            removed = change.get("removed", False)
            file_meta = change.get("file", {})
            trashed = file_meta.get("trashed", False)
            mime_type = file_meta.get("mimeType", "")

            # Skip types handled by dedicated providers
            if not removed and _should_skip(mime_type):
                continue

            # Handle deleted/trashed files
            if removed or trashed:
                s3_service.delete_key(s3_service.raw_key(agent_id, "drive", file_id))
                counters["skipped"] += 1
                continue

            content = _extract_content(drive_service, file_meta)
            parsed = _parse_file(file_meta, content)

            if s3_service.save_raw(agent_id, "drive", file_id, parsed):
                counters["fetched"] += 1
            else:
                counters["failed"] += 1

            total = counters["fetched"] + counters["skipped"] + counters["failed"]
            _update_progress(
                "FETCHING",
                {
                    "stage": "fetching",
                    "message": f"Syncing files ({counters['fetched']} updated, {counters['skipped']} removed)...",
                    "current": counters["fetched"],
                    "total": total,
                    "percentage": 0,
                    "skipped": counters["skipped"],
                    "failed": counters["failed"],
                },
            )

        next_page = response.get("nextPageToken")
        new_start_page_token = response.get("newStartPageToken")

        if next_page:
            page_token = next_page
            time.sleep(_INTER_PAGE_DELAY)
        else:
            break

    return new_start_page_token
