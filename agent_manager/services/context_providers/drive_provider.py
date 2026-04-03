"""Google Drive context provider implementation.

Indexes PDFs, plain text files, and metadata for all other non-Doc/Sheet files.
Explicitly skips Google Docs and Sheets (handled by dedicated providers).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from sqlalchemy.orm import Session

from .base import IntegrationContextProvider


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _mime_label(mime_type: str) -> str:
    """Human-readable label for common MIME types."""
    labels = {
        "application/pdf": "PDF",
        "text/plain": "Text",
        "text/markdown": "Markdown",
        "text/csv": "CSV",
        "text/html": "HTML",
        "application/json": "JSON",
        "image/png": "Image (PNG)",
        "image/jpeg": "Image (JPEG)",
        "video/mp4": "Video (MP4)",
        "application/vnd.google-apps.folder": "Folder",
        "application/vnd.google-apps.drawing": "Drawing",
    }
    return labels.get(mime_type, mime_type.split("/")[-1] if "/" in mime_type else mime_type)


class DriveContextProvider(IntegrationContextProvider):

    # ── Identity ──────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "google_drive"

    @property
    def display_name(self) -> str:
        return "Google Drive"

    @property
    def dedup_key(self) -> str:
        return "file_id"

    # ── Credentials ───────────────────────────────────────────────────────

    def verify_credentials(self, db: Session, agent_id: str) -> bool:
        from agent_manager.integrations.google.drive.service import get_service
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
        from agent_manager.integrations.google.drive.search_service import snapshot
        return snapshot(agent_id, hours=hours)

    def format_snapshot_lines(self, results: list[dict], max_items: int = 10) -> list[str]:
        lines: list[str] = []
        for item in results[:max_items]:
            title = item.get("title", "Untitled")
            modified = item.get("modified_time", "")
            owner = item.get("owner", "")
            mime = _mime_label(item.get("mime_type", ""))
            shared_str = " (shared)" if item.get("shared") else ""
            snippet = _truncate(item.get("snippet", ""), 150)
            line = f"• [{modified}] {title} [{mime}] — {owner}{shared_str}"
            if snippet:
                line += f"\n  Preview: {snippet}"
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
            mime = _mime_label(item.get("mime_type", ""))
            shared_str = " (shared)" if item.get("shared") else ""
            snippet = _truncate(item.get("snippet", ""), snippet_max_len)
            line = f"{i}. {title} [{mime}] | Owner: {owner} | Modified: {modified}{shared_str}"
            if snippet:
                line += f"\n   {snippet}"
            lines.append(line)
        return lines

    def context_block_header(self) -> str:
        return "--- Drive Context ---"

    def snapshot_label(self) -> str:
        return "Recently modified files (last 7 days):"

    def semantic_label(self) -> str:
        return "Relevant files for your query:"

    def context_block_footer(self) -> str:
        return "---------------------"

    @property
    def default_snapshot_hours(self) -> int:
        return 168  # 7 days

    # ── Ingest hooks ──────────────────────────────────────────────────────

    @property
    def s3_integration_key(self) -> str:
        return "drive"

    @property
    def qdrant_source(self) -> str:
        return "google_drive"

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
        from agent_manager.tasks.drive.ingest_task import _full_sync
        return _full_sync(api_service, agent_id, counters, is_aborted)

    def incremental_sync(
        self, api_service: Any, agent_id: str, cursor: str,
        counters: dict[str, int], is_aborted: Any,
    ) -> str | None:
        from agent_manager.tasks.drive.ingest_task import _incremental_sync
        return _incremental_sync(api_service, agent_id, cursor, counters, is_aborted)

    def list_s3_item_ids(self, agent_id: str) -> list[str]:
        from agent_manager.services import s3_service
        return s3_service.list_item_ids(agent_id, "drive")

    def load_s3_batch(self, agent_id: str, item_ids: list[str]) -> list[dict]:
        from agent_manager.services import s3_service
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(s3_service.load_raw, agent_id, "drive", fid): fid
                for fid in item_ids
            }
            results: dict[str, dict] = {}
            for future in as_completed(futures):
                fid = futures[future]
                raw = future.result()
                if raw:
                    results[fid] = raw
        return [results[fid] for fid in item_ids if fid in results]

    def pipeline_batch(
        self, items: list[dict], agent_id: str, account_email: str,
    ) -> None:
        from agent_manager.integrations.google.drive.pipeline_service import process_drive_batch
        process_drive_batch(items, agent_id, account_email)

    def pipeline_single(
        self, item: dict, agent_id: str, account_email: str,
    ) -> None:
        from agent_manager.integrations.google.drive.pipeline_service import process_drive_file
        process_drive_file(item, agent_id, account_email)

    def delete_s3_data(self, agent_id: str, task_id: str, update_progress: Any) -> int:
        from agent_manager.services import s3_service
        return s3_service.delete_namespace(agent_id, "drive")
