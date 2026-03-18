"""Celery task helpers for bulk Calendar ingestion → S3."""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import redis as redis_lib
from celery import current_task

from agent_manager.config import settings
from agent_manager.services import s3_service

logger = logging.getLogger(__name__)

# Redis hash that maps "integration:agent_id" -> task_id for in-flight jobs.
_ACTIVE_KEY = "openclaw:ingest:active"
_ACTIVE_TTL = 86_400  # 24 hours


# ── Active-task Registry ──────────────────────────────────────────────────────

def _redis() -> redis_lib.Redis:
    return redis_lib.from_url(settings.REDIS_URL, decode_responses=True)


def _active_field(agent_id: str, task_type: str = "ingest") -> str:
    return f"google_calendar:{task_type}:{agent_id}"


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


# ── Event Parsing ────────────────────────────────────────────────────────────

def _parse_event(event: dict) -> dict:
    """Parse a raw Calendar API event into a clean dict for S3 storage."""
    start = event.get("start", {})
    end = event.get("end", {})
    organizer = event.get("organizer", {})

    return {
        "id": event["id"],
        "summary": event.get("summary", ""),
        "description": event.get("description", ""),
        "start": start.get("dateTime", start.get("date", "")),
        "end": end.get("dateTime", end.get("date", "")),
        "location": event.get("location", ""),
        "organizer": organizer.get("email", organizer.get("displayName", "")),
        "attendees": event.get("attendees", []),
        "status": event.get("status", ""),
        "recurringEventId": event.get("recurringEventId", ""),
        "htmlLink": event.get("htmlLink", ""),
        "created": event.get("created", ""),
        "updated": event.get("updated", ""),
    }


# ── Sync Strategies ───────────────────────────────────────────────────────────

def _full_sync(
    service: Any,
    agent_id: str,
    counters: dict[str, int],
    is_aborted: Callable[[], bool],
) -> str | None:
    """Fetch ALL calendar events (past and future) and store in S3.

    Uses the Calendar API's events.list with no time bounds and singleEvents=True
    to expand recurring events. Returns the nextSyncToken for future incremental syncs.

    Returns:
        The nextSyncToken, or None if the task was cancelled.
    """
    # Pre-scan S3 to skip already-stored events
    stored_ids = set(_list_calendar_event_ids(agent_id))

    page_token: str | None = None
    sync_token: str | None = None

    while True:
        if is_aborted():
            return None

        kwargs: dict[str, Any] = {
            "calendarId": "primary",
            "maxResults": 2500,
            # NOTE: orderBy and singleEvents are intentionally omitted.
            # The Calendar API only returns nextSyncToken when orderBy is NOT set.
        }
        if page_token:
            kwargs["pageToken"] = page_token

        response = service.events().list(**kwargs).execute()
        events = response.get("items", [])

        for event in events:
            if is_aborted():
                return None

            event_id = event.get("id")
            if not event_id:
                continue

            if event_id in stored_ids:
                counters["skipped"] += 1
                continue

            parsed = _parse_event(event)
            if s3_service.save_calendar_raw(agent_id, event_id, parsed):
                counters["fetched"] += 1
                stored_ids.add(event_id)
            else:
                counters["failed"] += 1

            # Emit progress after each individual event
            total = counters["fetched"] + counters["skipped"] + counters["failed"]
            _update_progress(
                "FETCHING",
                {
                    "stage": "fetching",
                    "message": f"Fetching calendar events ({counters['fetched']} new, {counters['skipped']} skipped)...",
                    "current": counters["fetched"],
                    "total": total,
                    "percentage": 0,
                    "skipped": counters["skipped"],
                    "failed": counters["failed"],
                },
            )

        page_token = response.get("nextPageToken")
        sync_token = response.get("nextSyncToken")
        if not page_token:
            break

    return sync_token


def _incremental_sync(
    service: Any,
    agent_id: str,
    sync_token: str,
    counters: dict[str, int],
    is_aborted: Callable[[], bool],
) -> str | None:
    """Fetch only events changed since the last sync using the syncToken.

    Returns:
        The new nextSyncToken, or None if the task was cancelled.
    """
    page_token: str | None = None
    new_sync_token: str | None = None

    while True:
        if is_aborted():
            return None

        kwargs: dict[str, Any] = {
            "calendarId": "primary",
            "syncToken": sync_token,
        }
        if page_token:
            kwargs["pageToken"] = page_token

        response = service.events().list(**kwargs).execute()
        events = response.get("items", [])

        for event in events:
            if is_aborted():
                return None

            event_id = event.get("id")
            if not event_id:
                continue

            # For cancelled events, remove from S3
            if event.get("status") == "cancelled":
                s3_service.delete_key(s3_service.calendar_raw_key(agent_id, event_id))
                counters["skipped"] += 1
                continue

            parsed = _parse_event(event)
            if s3_service.save_calendar_raw(agent_id, event_id, parsed):
                counters["fetched"] += 1
            else:
                counters["failed"] += 1

            # Emit progress after each event
            total = counters["fetched"] + counters["skipped"] + counters["failed"]
            _update_progress(
                "FETCHING",
                {
                    "stage": "fetching",
                    "message": f"Syncing calendar events ({counters['fetched']} updated, {counters['skipped']} removed)...",
                    "current": counters["fetched"],
                    "total": total,
                    "percentage": 0,
                    "skipped": counters["skipped"],
                    "failed": counters["failed"],
                },
            )

        page_token = response.get("nextPageToken")
        new_sync_token = response.get("nextSyncToken")
        if not page_token:
            break

    return new_sync_token


# ── S3 Helpers ───────────────────────────────────────────────────────────────

def _list_calendar_event_ids(agent_id: str) -> list[str]:
    """Return event IDs stored in S3 for this agent."""
    prefix = f"{agent_id}/calendar/raw/"
    keys = s3_service.list_keys(prefix)
    return [k.replace(prefix, "").replace(".json", "") for k in keys]
