"""Gmail context provider implementation."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from sqlalchemy.orm import Session

from .base import IntegrationContextProvider


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


class GmailContextProvider(IntegrationContextProvider):

    # ── Identity ──────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "gmail"

    @property
    def display_name(self) -> str:
        return "Gmail"

    @property
    def dedup_key(self) -> str:
        return "message_id"

    # ── Credentials ───────────────────────────────────────────────────────

    def verify_credentials(self, db: Session, agent_id: str) -> bool:
        from agent_manager.integrations.google.gmail.service import get_service
        return get_service(db, agent_id) is not None

    # ── Celery tasks ──────────────────────────────────────────────────────

    def get_ingest_task(self):
        from agent_manager.tasks.generic_context_task import ingest_and_pipeline
        return ingest_and_pipeline

    def get_delete_task(self):
        from agent_manager.tasks.generic_context_task import delete_context_data
        return delete_context_data

    # ── Snapshot & formatting ─────────────────────────────────────────────

    def snapshot(self, agent_id: str, hours: int = 24) -> list[dict]:
        from agent_manager.integrations.google.gmail.search_service import snapshot
        return snapshot(agent_id, hours=hours)

    def format_snapshot_lines(self, results: list[dict], max_items: int = 10) -> list[str]:
        lines: list[str] = []
        for item in results[:max_items]:
            date = item.get("date", "")
            sender = item.get("from", "")
            subject = item.get("subject", "")
            lines.append(f"• [{date}] From: {sender} | Subject: {subject}")
        return lines

    def format_semantic_lines(
        self, results: list[dict], max_items: int = 5, snippet_max_len: int = 200,
    ) -> list[str]:
        lines: list[str] = []
        for i, item in enumerate(results[:max_items], 1):
            sender = item.get("from", "")
            date = item.get("date", "")
            subject = item.get("subject", "")
            snippet = _truncate(item.get("snippet", ""), snippet_max_len)
            lines.append(
                f"{i}. From: {sender} | Date: {date} | Subject: {subject}\n"
                f"   {snippet}"
            )
        return lines

    def context_block_header(self) -> str:
        return "--- Email Context ---"

    def snapshot_label(self) -> str:
        return "Recent activity (last 24h):"

    def semantic_label(self) -> str:
        return "Relevant emails for your query:"

    def context_block_footer(self) -> str:
        return "--------------------"

    @property
    def default_snapshot_hours(self) -> int:
        return 24

    # ── Ingest hooks ──────────────────────────────────────────────────────

    @property
    def s3_integration_key(self) -> str:
        return "gmail"

    @property
    def qdrant_source(self) -> str:
        return "gmail"

    @property
    def expired_sync_cursor_http_code(self) -> int:
        return 404  # Gmail history ID too old

    def build_api_service(self, credentials: Any) -> Any:
        from googleapiclient.discovery import build
        return build("gmail", "v1", credentials=credentials)

    def get_account_email(self, api_service: Any) -> str:
        profile = api_service.users().getProfile(userId="me").execute()
        return profile.get("emailAddress", "")

    def full_sync(
        self, api_service: Any, agent_id: str, counters: dict[str, int],
        is_aborted: Any,
    ) -> str | None:
        from agent_manager.integrations.google.gmail.auth_service import get_valid_credentials
        from agent_manager.tasks.gmail.ingest_task import _full_sync
        from agent_manager.database import SessionLocal
        # Gmail full sync needs credentials and counter_lock for concurrent batching
        import threading
        db = SessionLocal()
        try:
            creds = get_valid_credentials(db, agent_id)
            profile = api_service.users().getProfile(userId="me").execute()
            total_estimate = profile.get("messagesTotal", 0)
            return _full_sync(
                api_service, agent_id, total_estimate, counters, is_aborted,
                creds, threading.Lock(),
            )
        finally:
            db.close()

    def incremental_sync(
        self, api_service: Any, agent_id: str, cursor: str,
        counters: dict[str, int], is_aborted: Any,
    ) -> str | None:
        from agent_manager.integrations.google.gmail.auth_service import get_valid_credentials
        from agent_manager.tasks.gmail.ingest_task import _incremental_sync
        from agent_manager.database import SessionLocal
        import threading
        db = SessionLocal()
        try:
            creds = get_valid_credentials(db, agent_id)
            return _incremental_sync(
                api_service, agent_id, cursor, counters, is_aborted,
                creds, threading.Lock(),
            )
        finally:
            db.close()

    def list_s3_item_ids(self, agent_id: str) -> list[str]:
        from agent_manager.services import s3_service
        return s3_service.list_gmail_message_ids(agent_id)

    def load_s3_batch(self, agent_id: str, item_ids: list[str]) -> list[dict]:
        from agent_manager.services import s3_service
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(s3_service.load_gmail_raw, agent_id, mid): mid
                for mid in item_ids
            }
            results: dict[str, dict] = {}
            for future in as_completed(futures):
                mid = futures[future]
                raw = future.result()
                if raw:
                    results[mid] = raw
        return [results[mid] for mid in item_ids if mid in results]

    def pipeline_batch(
        self, items: list[dict], agent_id: str, account_email: str,
    ) -> None:
        from agent_manager.integrations.google.gmail.pipeline_service import process_messages_batch
        process_messages_batch(items, agent_id, account_email)

    def pipeline_single(
        self, item: dict, agent_id: str, account_email: str,
    ) -> None:
        from agent_manager.integrations.google.gmail.pipeline_service import process_message
        process_message(item, agent_id, account_email)

    def delete_s3_data(self, agent_id: str, task_id: str, update_progress: Any) -> int:
        from agent_manager.services import s3_service

        def _on_s3_progress(tagged: int, total: int) -> None:
            percentage = int((tagged / total * 100) if total else 0)
            update_progress(
                "DELETING",
                {
                    "stage": "expiring_s3",
                    "message": f"Marking emails as expired ({tagged}/{total})...",
                    "current": tagged,
                    "total": total,
                    "percentage": percentage,
                    "task_id": task_id,
                },
            )

        return s3_service.tag_gmail_as_expired(agent_id, progress_callback=_on_s3_progress)
