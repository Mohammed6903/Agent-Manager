"""Google Sheets context provider implementation."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from sqlalchemy.orm import Session

from .base import IntegrationContextProvider


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


class SheetsContextProvider(IntegrationContextProvider):

    @property
    def name(self) -> str:
        return "google_sheets"

    @property
    def display_name(self) -> str:
        return "Google Sheets"

    @property
    def dedup_key(self) -> str:
        return "sheet_id"

    def verify_credentials(self, db: Session, agent_id: str) -> bool:
        from agent_manager.integrations.google.sheets.service import get_service
        return get_service(db, agent_id) is not None

    def get_ingest_task(self):
        from agent_manager.tasks.generic_context_task import ingest_and_pipeline
        return ingest_and_pipeline

    def get_delete_task(self):
        from agent_manager.tasks.generic_context_task import delete_context_data
        return delete_context_data

    def snapshot(self, agent_id: str, hours: int = 168) -> list[dict]:
        from agent_manager.integrations.google.sheets.search_service import snapshot
        return snapshot(agent_id, hours=hours)

    def format_snapshot_lines(self, results: list[dict], max_items: int = 10) -> list[str]:
        lines: list[str] = []
        for item in results[:max_items]:
            title = item.get("title", "Untitled")
            modified = item.get("modified_time", "")
            owner = item.get("owner", "")
            snippet = _truncate(item.get("snippet", ""), 150)
            shared_str = " (shared)" if item.get("shared") else ""
            line = f"• [{modified}] {title} — {owner}{shared_str}"
            if snippet:
                line += f"\n  Content preview: {snippet}"
            lines.append(line)
        return lines

    def format_semantic_lines(
        self, results: list[dict], max_items: int = 5, snippet_max_len: int = 200,
    ) -> list[str]:
        lines: list[str] = []
        for i, item in enumerate(results[:max_items], 1):
            title = item.get("title", "Untitled")
            owner = item.get("owner", "")
            modified = item.get("modified_time", "")
            snippet = _truncate(item.get("snippet", ""), snippet_max_len)
            shared_str = " (shared)" if item.get("shared") else ""
            line = f"{i}. {title} | Owner: {owner} | Modified: {modified}{shared_str}"
            if snippet:
                line += f"\n   {snippet}"
            lines.append(line)
        return lines

    def context_block_header(self) -> str:
        return "--- Sheets Context ---"

    def snapshot_label(self) -> str:
        return "Recently modified spreadsheets (last 7 days):"

    def semantic_label(self) -> str:
        return "Relevant spreadsheets for your query:"

    def context_block_footer(self) -> str:
        return "----------------------"

    @property
    def default_snapshot_hours(self) -> int:
        return 168

    # ── Ingest hooks ──────────────────────────────────────────────────────

    @property
    def s3_integration_key(self) -> str:
        return "sheets"

    @property
    def qdrant_source(self) -> str:
        return "google_sheets"

    @property
    def expired_sync_cursor_http_code(self) -> int:
        return 403

    def build_api_service(self, credentials: Any) -> Any:
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=credentials)

    def get_account_email(self, api_service: Any) -> str:
        try:
            about = api_service.about().get(fields="user(emailAddress)").execute()
            return about.get("user", {}).get("emailAddress", "")
        except Exception:
            return ""

    def full_sync(
        self, api_service: Any, agent_id: str, counters: dict[str, int],
        is_aborted: Any,
    ) -> str | None:
        from agent_manager.tasks.sheets.ingest_task import _full_sync
        return _full_sync(api_service, agent_id, counters, is_aborted)

    def incremental_sync(
        self, api_service: Any, agent_id: str, cursor: str,
        counters: dict[str, int], is_aborted: Any,
    ) -> str | None:
        from agent_manager.tasks.sheets.ingest_task import _incremental_sync
        return _incremental_sync(api_service, agent_id, cursor, counters, is_aborted)

    def list_s3_item_ids(self, agent_id: str) -> list[str]:
        from agent_manager.services import s3_service
        return s3_service.list_item_ids(agent_id, "sheets")

    def load_s3_batch(self, agent_id: str, item_ids: list[str]) -> list[dict]:
        from agent_manager.services import s3_service
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(s3_service.load_raw, agent_id, "sheets", sid): sid
                for sid in item_ids
            }
            results: dict[str, dict] = {}
            for future in as_completed(futures):
                sid = futures[future]
                raw = future.result()
                if raw:
                    results[sid] = raw
        return [results[sid] for sid in item_ids if sid in results]

    def pipeline_batch(
        self, items: list[dict], agent_id: str, account_email: str,
    ) -> None:
        from agent_manager.integrations.google.sheets.pipeline_service import process_sheets_batch
        process_sheets_batch(items, agent_id, account_email)

    def pipeline_single(
        self, item: dict, agent_id: str, account_email: str,
    ) -> None:
        from agent_manager.integrations.google.sheets.pipeline_service import process_sheet
        process_sheet(item, agent_id, account_email)

    def delete_s3_data(self, agent_id: str, task_id: str, update_progress: Any) -> int:
        from agent_manager.services import s3_service
        return s3_service.delete_namespace(agent_id, "sheets")
