"""Google Calendar context provider implementation."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from sqlalchemy.orm import Session

from .base import IntegrationContextProvider


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


class CalendarContextProvider(IntegrationContextProvider):

    # ── Identity ──────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "google_calendar"

    @property
    def display_name(self) -> str:
        return "Google Calendar"

    @property
    def dedup_key(self) -> str:
        return "event_id"

    # ── Credentials ───────────────────────────────────────────────────────

    def verify_credentials(self, db: Session, agent_id: str) -> bool:
        from agent_manager.integrations.google.calendar.service import get_service
        return get_service(db, agent_id) is not None

    # ── Celery tasks ──────────────────────────────────────────────────────

    def get_ingest_task(self):
        from agent_manager.tasks.generic_context_task import ingest_and_pipeline
        return ingest_and_pipeline

    def get_delete_task(self):
        from agent_manager.tasks.generic_context_task import delete_context_data
        return delete_context_data

    # ── Snapshot & formatting ─────────────────────────────────────────────

    def snapshot(self, agent_id: str, hours: int = 168) -> list[dict]:
        from agent_manager.integrations.google.calendar.search_service import snapshot
        return snapshot(agent_id, hours=hours)

    def format_snapshot_lines(self, results: list[dict], max_items: int = 10) -> list[str]:
        lines: list[str] = []
        for item in results[:max_items]:
            start = item.get("start", "")
            summary = item.get("summary", "No title")
            location = item.get("location", "")
            loc_str = f" @ {location}" if location else ""
            lines.append(f"• [{start}] {summary}{loc_str}")
        return lines

    def format_semantic_lines(
        self, results: list[dict], max_items: int = 5, snippet_max_len: int = 200,
    ) -> list[str]:
        lines: list[str] = []
        for i, item in enumerate(results[:max_items], 1):
            summary = item.get("summary", "No title")
            start = item.get("start", "")
            end = item.get("end", "")
            location = item.get("location", "")
            attendees = item.get("attendees", "")
            loc_str = f" | Location: {location}" if location else ""
            att_str = f" | Attendees: {_truncate(attendees, 100)}" if attendees else ""
            lines.append(
                f"{i}. {summary} | {start} → {end}{loc_str}{att_str}"
            )
        return lines

    def context_block_header(self) -> str:
        return "--- Calendar Context ---"

    def snapshot_label(self) -> str:
        return "Upcoming events (next 7 days):"

    def semantic_label(self) -> str:
        return "Relevant calendar events for your query:"

    def context_block_footer(self) -> str:
        return "------------------------"

    @property
    def default_snapshot_hours(self) -> int:
        return 168  # 7 days

    # ── Ingest hooks ──────────────────────────────────────────────────────

    @property
    def s3_integration_key(self) -> str:
        return "calendar"

    @property
    def qdrant_source(self) -> str:
        return "google_calendar"

    @property
    def expired_sync_cursor_http_code(self) -> int:
        return 410  # Calendar sync token gone

    def build_api_service(self, credentials: Any) -> Any:
        from googleapiclient.discovery import build
        return build("calendar", "v3", credentials=credentials)

    def get_account_email(self, api_service: Any) -> str:
        try:
            cal = api_service.calendars().get(calendarId="primary").execute()
            return cal.get("id", "")
        except Exception:
            return ""

    def full_sync(
        self, api_service: Any, agent_id: str, counters: dict[str, int],
        is_aborted: Any,
    ) -> str | None:
        from agent_manager.tasks.calendar.ingest_task import _full_sync
        return _full_sync(api_service, agent_id, counters, is_aborted)

    def incremental_sync(
        self, api_service: Any, agent_id: str, cursor: str,
        counters: dict[str, int], is_aborted: Any,
    ) -> str | None:
        from agent_manager.tasks.calendar.ingest_task import _incremental_sync
        return _incremental_sync(api_service, agent_id, cursor, counters, is_aborted)

    def list_s3_item_ids(self, agent_id: str) -> list[str]:
        from agent_manager.services import s3_service
        return s3_service.list_calendar_event_ids(agent_id)

    def load_s3_batch(self, agent_id: str, item_ids: list[str]) -> list[dict]:
        from agent_manager.services import s3_service
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(s3_service.load_calendar_raw, agent_id, eid): eid
                for eid in item_ids
            }
            results: dict[str, dict] = {}
            for future in as_completed(futures):
                eid = futures[future]
                raw = future.result()
                if raw:
                    results[eid] = raw
        return [results[eid] for eid in item_ids if eid in results]

    def pipeline_batch(
        self, items: list[dict], agent_id: str, account_email: str,
    ) -> None:
        from agent_manager.integrations.google.calendar.pipeline_service import process_events_batch
        process_events_batch(items, agent_id, account_email)

    def pipeline_single(
        self, item: dict, agent_id: str, account_email: str,
    ) -> None:
        from agent_manager.integrations.google.calendar.pipeline_service import process_event
        process_event(item, agent_id, account_email)

    def delete_s3_data(self, agent_id: str, task_id: str, update_progress: Any) -> int:
        from agent_manager.services import s3_service
        prefix = f"{agent_id}/calendar/"
        keys = s3_service.list_keys(prefix)
        for key in keys:
            s3_service.delete_key(key)
        return len(keys)
