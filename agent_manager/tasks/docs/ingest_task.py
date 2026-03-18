"""Celery task helpers for bulk Google Docs ingestion → S3 via Drive API."""
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

_DOCS_MIME_TYPE = "application/vnd.google-apps.document"
# Courtesy delay between export batches to avoid rate-limiting
_INTER_PAGE_DELAY: float = 0.5
# Max docs to export per page request
_PAGE_SIZE = 100

# ── Active-task Registry ──────────────────────────────────────────────────────

_ACTIVE_KEY = "openclaw:ingest:active"
_ACTIVE_TTL = 86_400


def _redis() -> redis_lib.Redis:
    return redis_lib.from_url(settings.REDIS_URL, decode_responses=True)


def _active_field(agent_id: str, task_type: str = "ingest") -> str:
    return f"google_docs:{task_type}:{agent_id}"


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


# ── Doc Content Export ───────────────────────────────────────────────────────

def _export_doc_as_text(drive_service: Any, file_id: str) -> str | None:
    """Export a Google Doc as plain text via Drive API.

    Returns the text content, or None if export fails.
    """
    try:
        response = drive_service.files().export(
            fileId=file_id,
            mimeType="text/plain",
        ).execute()
        if isinstance(response, bytes):
            return response.decode("utf-8", errors="replace")
        return str(response)
    except Exception:
        logger.warning("Failed to export doc %s as text", file_id, exc_info=True)
        return None


def _parse_doc(file_meta: dict, content: str) -> dict:
    """Build a clean dict for S3 storage from Drive file metadata + exported text."""
    owners = file_meta.get("owners", [])
    owner_email = owners[0].get("emailAddress", "") if owners else ""

    return {
        "id": file_meta["id"],
        "title": file_meta.get("name", ""),
        "owner": owner_email,
        "content": content,
        "modified_time": file_meta.get("modifiedTime", ""),
        "created_time": file_meta.get("createdTime", ""),
        "web_view_link": file_meta.get("webViewLink", ""),
        "mime_type": file_meta.get("mimeType", _DOCS_MIME_TYPE),
        "shared": file_meta.get("shared", False),
    }


# ── Sync Strategies ───────────────────────────────────────────────────────────

def _full_sync(
    drive_service: Any,
    agent_id: str,
    counters: dict[str, int],
    is_aborted: Callable[[], bool],
) -> str | None:
    """Fetch ALL Google Docs via Drive API, export as text, store in S3.

    Uses Drive files.list filtered to Google Docs MIME type.
    Returns the Drive changes startPageToken for future incremental syncs,
    or None if aborted.
    """
    # Get the current startPageToken BEFORE scanning — anything that changes
    # after this point will be picked up by the next incremental sync.
    start_token_resp = drive_service.changes().getStartPageToken().execute()
    start_page_token: str = start_token_resp["startPageToken"]

    # Pre-scan S3 to skip already-stored docs
    stored_ids = set(s3_service.list_item_ids(agent_id, "docs"))

    page_token: str | None = None

    while True:
        if is_aborted():
            return None

        kwargs: dict[str, Any] = {
            "q": f"mimeType='{_DOCS_MIME_TYPE}' and trashed=false",
            "pageSize": _PAGE_SIZE,
            "fields": "nextPageToken, files(id, name, mimeType, modifiedTime, createdTime, webViewLink, owners, shared)",
        }
        if page_token:
            kwargs["pageToken"] = page_token

        response = drive_service.files().list(**kwargs).execute()
        files = response.get("files", [])

        for file_meta in files:
            if is_aborted():
                return None

            file_id = file_meta.get("id")
            if not file_id:
                continue

            if file_id in stored_ids:
                counters["skipped"] += 1
                continue

            content = _export_doc_as_text(drive_service, file_id)
            if content is None:
                counters["failed"] += 1
                continue

            parsed = _parse_doc(file_meta, content)
            if s3_service.save_raw(agent_id, "docs", file_id, parsed):
                counters["fetched"] += 1
                stored_ids.add(file_id)
            else:
                counters["failed"] += 1

            # Emit progress after each individual doc
            total = counters["fetched"] + counters["skipped"] + counters["failed"]
            _update_progress(
                "FETCHING",
                {
                    "stage": "fetching",
                    "message": f"Fetching docs ({counters['fetched']} new, {counters['skipped']} skipped)...",
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
    """Fetch only docs changed since last sync using Drive changes API.

    Returns the new startPageToken, or None if aborted.
    """
    new_start_page_token: str | None = None

    while True:
        if is_aborted():
            return None

        response = drive_service.changes().list(
            pageToken=page_token,
            spaces="drive",
            fields="nextPageToken, newStartPageToken, changes(fileId, removed, file(id, name, mimeType, modifiedTime, createdTime, webViewLink, owners, shared, trashed))",
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

            # Skip non-doc files
            if not removed and mime_type != _DOCS_MIME_TYPE:
                continue

            # Handle deleted/trashed docs — remove from S3
            if removed or trashed:
                s3_service.delete_key(s3_service.raw_key(agent_id, "docs", file_id))
                counters["skipped"] += 1
                continue

            # Re-export the changed doc
            content = _export_doc_as_text(drive_service, file_id)
            if content is None:
                counters["failed"] += 1
                continue

            parsed = _parse_doc(file_meta, content)
            if s3_service.save_raw(agent_id, "docs", file_id, parsed):
                counters["fetched"] += 1
            else:
                counters["failed"] += 1

            # Emit progress after each doc
            total = counters["fetched"] + counters["skipped"] + counters["failed"]
            _update_progress(
                "FETCHING",
                {
                    "stage": "fetching",
                    "message": f"Syncing docs ({counters['fetched']} updated, {counters['skipped']} removed)...",
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
