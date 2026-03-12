"""Celery task — unified Gmail ingest (→ S3) + pipeline (→ Qdrant) per ThirdPartyContext."""
from __future__ import annotations

import threading
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from celery.contrib.abortable import AbortableTask
from googleapiclient.errors import HttpError

from ..celery_app import celery_app
from ..database import SessionLocal
from ..repositories.gmail_sync_repository import GmailSyncRepository
from ..repositories.third_party_context_repository import ThirdPartyContextRepository
from ..services import gmail_pipeline_service, qdrant_service, s3_service
from ..services.gmail_auth_service import get_valid_credentials
from .gmail_ingest_task import (
    _full_sync,
    _incremental_sync,
    _update_progress,
    register_active_task,
    unregister_active_task,
)

logger = logging.getLogger(__name__)

_PIPELINE_BATCH_SIZE = 200  # was 50 — token fix gives ~7x more budget headroom


def _load_batch_s3(agent_id: str, message_ids: list[str]) -> list[dict]:
    """Fetch a batch of S3 email objects in parallel.

    Args:
        agent_id: Agent whose S3 namespace to read from.
        message_ids: IDs to fetch in this batch.

    Returns:
        List of raw dicts (in original order) for IDs that were found in S3.
        Missing/None results are silently dropped.
    """
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(s3_service.load_gmail_raw, agent_id, mid): mid
            for mid in message_ids
        }
        results: dict[str, dict] = {}
        for future in as_completed(futures):
            mid = futures[future]
            raw = future.result()
            if raw:
                results[mid] = raw
    return [results[mid] for mid in message_ids if mid in results]


def _set_ctx_status(db: Any, ctx_id: uuid.UUID, status: str) -> None:
    """Best-effort status update — never raises so it cannot mask the real error."""
    try:
        ThirdPartyContextRepository(db).update_status(ctx_id, status)
    except Exception:
        logger.exception(
            "Failed to update ThirdPartyContext %s → %s.", ctx_id, status
        )


@celery_app.task(bind=True, base=AbortableTask, max_retries=3)
def ingest_and_pipeline_gmail(
    self, agent_id: str, context_id: str, force_full_sync: bool = False
) -> dict[str, object]:
    """Ingest Gmail emails to S3, then run the embedding pipeline to Qdrant.

    Args:
        agent_id: ID of the agent whose Gmail mailbox to sync.
        context_id: UUID string of the ThirdPartyContext tracking row.
        force_full_sync: When True, clear any stored historyId so the task
            performs a full re-sync from scratch instead of an incremental one.
    """
    task_id: str = self.request.id
    ctx_id = uuid.UUID(context_id)
    db = SessionLocal()

    try:
        register_active_task(agent_id, task_id)
        ctx_repo = ThirdPartyContextRepository(db)
        sync_repo = GmailSyncRepository(db)
        ctx_repo.update_task(ctx_id, task_id, "ingesting")

        if force_full_sync:
            logger.info("force_full_sync=True: clearing sync state for agent %s.", agent_id)
            sync_repo.clear(agent_id)

        # ── Phase 1: Ingest ───────────────────────────────────────────────────
        _update_progress(
            "FETCHING",
            {
                "stage": "counting",
                "message": "Counting total emails...",
                "fetched": 0,
                "total": 0,
                "skipped": 0,
                "failed": 0,
                "task_id": task_id,
            },
        )

        creds = get_valid_credentials(db, agent_id)
        if not creds:
            raise RuntimeError("Gmail service unavailable — check OAuth credentials")

        from googleapiclient.discovery import build as _build_svc  # noqa: PLC0415

        service = _build_svc("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        account_email: str = profile.get("emailAddress", "")
        total_estimate: int = profile.get("messagesTotal", 0)
        counter_lock = threading.Lock()
        # Capture task_id into a thread-safe closure — self.request.id is a
        # Celery thread-local and resolves to None inside ThreadPoolExecutor workers.
        _captured_task_id = task_id
        is_aborted = lambda: self.is_aborted(task_id=_captured_task_id)  # noqa: E731

        counters: dict[str, int] = {"fetched": 0, "skipped": 0, "failed": 0}
        sync_state = sync_repo.get(agent_id)
        new_history_id: str | None

        if sync_state and sync_state.history_id:
            _update_progress(
                "FETCHING",
                {
                    "stage": "fetching",
                    "message": "Fetching new emails since last sync...",
                    "fetched": 0,
                    "total": 0,
                    "skipped": 0,
                    "failed": 0,
                    "task_id": task_id,
                },
            )
            try:
                new_history_id = _incremental_sync(
                    service,
                    agent_id,
                    sync_state.history_id,
                    counters,
                    is_aborted,
                    creds,
                    counter_lock,
                )
            except HttpError as exc:
                if exc.status_code == 404:
                    # History ID too old — fall back to a full sync
                    logger.warning(
                        "History ID expired for agent_id=%s, falling back to full sync.",
                        agent_id,
                    )
                    sync_repo.clear(agent_id)
                    counters = {"fetched": 0, "skipped": 0, "failed": 0}
                    _update_progress(
                        "FETCHING",
                        {
                            "stage": "fetching",
                            "message": (
                                f"Starting full fetch of ~{total_estimate} emails"
                            ),
                            "fetched": 0,
                            "total": total_estimate,
                            "skipped": 0,
                            "failed": 0,
                            "task_id": task_id,
                        },
                    )
                    new_history_id = _full_sync(
                        service,
                        agent_id,
                        total_estimate,
                        counters,
                        is_aborted,
                        creds,
                        counter_lock,
                    )
                else:
                    raise
        else:
            _update_progress(
                "FETCHING",
                {
                    "stage": "fetching",
                    "message": f"Starting fetch of ~{total_estimate} emails",
                    "fetched": 0,
                    "total": total_estimate,
                    "skipped": 0,
                    "failed": 0,
                    "task_id": task_id,
                },
            )
            new_history_id = _full_sync(
                service, agent_id, total_estimate, counters, is_aborted, creds, counter_lock
            )

        # Cancelled mid-ingest
        if new_history_id is None:
            _set_ctx_status(db, ctx_id, "cancelled")
            _update_progress(
                "REVOKED",
                {
                    "stage": "cancelled",
                    "message": "Ingestion cancelled.",
                    "task_id": task_id,
                    **counters,
                },
            )
            return {
                "stage": "cancelled",
                "message": "Ingestion cancelled.",
                "task_id": task_id,
                **counters,
            }

        sync_repo.save_history_id(
            agent_id, new_history_id, fetched_count=counters["fetched"]
        )
        ingest_result = dict(counters)

        # ── Phase 2: Pipeline ─────────────────────────────────────────────────
        ctx_repo.update_status(ctx_id, "processing")

        message_ids = s3_service.list_gmail_message_ids(agent_id)
        total_pipeline = len(message_ids)
        processed = failed = 0

        _update_progress(
            "PROCESSING",
            {
                "stage": "processing",
                "message": "Starting pipeline...",
                "processed": 0,
                "total": total_pipeline,
                "failed": 0,
                "task_id": task_id,
            },
        )

        for i in range(0, len(message_ids), _PIPELINE_BATCH_SIZE):
            if is_aborted():
                _set_ctx_status(db, ctx_id, "cancelled")
                logger.info(
                    "Pipeline phase aborted at %d/%d for task %s.",
                    processed,
                    total_pipeline,
                    task_id,
                )
                return {
                    "stage": "aborted",
                    "message": "Task was cancelled.",
                    "processed": processed,
                    "total": total_pipeline,
                    "failed": failed,
                    "task_id": task_id,
                }

            batch_ids = message_ids[i : i + _PIPELINE_BATCH_SIZE]
            raws = _load_batch_s3(agent_id, batch_ids)
            s3_misses = len(batch_ids) - len(raws)
            failed += s3_misses
            try:
                gmail_pipeline_service.process_messages_batch(raws, agent_id, account_email)
                processed += len(raws)
            except Exception:
                logger.exception(
                    "Pipeline batch failed for agent %s (batch starting at %d), retrying individually...",
                    agent_id,
                    i,
                )
                for raw in raws:
                    try:
                        gmail_pipeline_service.process_message(raw, agent_id, account_email)
                        processed += 1
                    except Exception:
                        failed += 1
                        logger.exception("Single message failed: %s", raw.get("id"))

            _update_progress(
                "PROCESSING",
                {
                    "stage": "processing",
                    "message": "Processing emails...",
                    "processed": processed,
                    "total": total_pipeline,
                    "failed": failed,
                    "task_id": task_id,
                },
            )

        ctx_repo.update_status(ctx_id, "complete")
        return {
            "stage": "complete",
            "message": "Ingest and pipeline complete.",
            "ingest": ingest_result,
            "processed": processed,
            "total": total_pipeline,
            "failed": failed,
            "task_id": task_id,
        }

    except Exception as exc:
        _set_ctx_status(db, ctx_id, "failed")
        _update_progress(
            "FAILED",
            {"stage": "error", "message": str(exc), "task_id": task_id},
        )
        raise self.retry(exc=exc, countdown=300)

    finally:
        unregister_active_task(agent_id, task_id)
        db.close()


@celery_app.task(bind=True, base=AbortableTask, max_retries=3)
def delete_gmail_context(
    self, agent_id: str, context_id: str
) -> dict[str, object]:
    """Delete all Gmail data (soft-delete S3, hard-delete Qdrant/DB).

    Deletion happens in stages with progress updates:
    1. Move S3 data to expired/ prefix (soft-delete, auto-cleanup in 30 days)
    2. Delete Qdrant embeddings (hard-delete)
    3. Delete context DB row (hard-delete, only if steps 1-2 succeed)

    DB row is ONLY deleted after S3 and Qdrant succeed, so if any step fails,
    the DB row remains as a recovery point for manual cleanup or retry.

    Emits progress updates so callers can poll the Celery result by task_id.

    Args:
        agent_id: Owner of the Gmail data namespace.
        context_id: UUID string of the ThirdPartyContext row to delete.
    """
    task_id: str = self.request.id
    ctx_id = uuid.UUID(context_id)
    db = SessionLocal()
    tagged_s3 = 0
    deleted_qdrant = 0

    try:
        # ── Step 1: Tag S3 objects as expired (soft-delete) ────────────────
        _update_progress(
            "DELETING",
            {
                "stage": "expiring_s3",
                "message": "Marking emails as expired (auto-deleted in 30 days)...",
                "progress": 0,
                "task_id": task_id,
            },
        )

        def _on_s3_progress(tagged: int, total: int) -> None:
            """Emit progress updates every 50 objects during S3 tagging."""
            _update_progress(
                "DELETING",
                {
                    "stage": "expiring_s3",
                    "message": f"Marking emails as expired ({tagged}/{total})...",
                    "progress": int((tagged / total * 100) if total else 0),
                    "tagged": tagged,
                    "total": total,
                    "task_id": task_id,
                },
            )

        try:
            tagged_s3 = s3_service.tag_gmail_as_expired(
                agent_id, progress_callback=_on_s3_progress
            )
            logger.info(
                "Tagged %d S3 objects as expired for agent %s (context %s).",
                tagged_s3,
                agent_id,
                context_id,
            )
        except Exception as s3_exc:
            logger.exception("S3 tagging failed for agent %s.", agent_id)
            _set_ctx_status(db, ctx_id, "delete_failed")
            _update_progress(
                "FAILED",
                {
                    "stage": "error",
                    "message": f"S3 soft-delete failed: {s3_exc}",
                    "task_id": task_id,
                },
            )
            raise

        # ── Step 2: Delete Qdrant vectors ─────────────────────────────────
        _update_progress(
            "DELETING",
            {
                "stage": "deleting_qdrant",
                "message": "Deleting vector embeddings from Qdrant...",
                "tagged_s3_objects": tagged_s3,
                "task_id": task_id,
            },
        )
        try:
            deleted_qdrant = qdrant_service.delete_points_for_agent_source(agent_id, "gmail")
            logger.info(
                "Deleted %d Qdrant points for agent %s (context %s).",
                deleted_qdrant,
                agent_id,
                context_id,
            )
        except Exception as qdrant_exc:
            logger.exception("Qdrant deletion failed for agent %s.", agent_id)
            _set_ctx_status(db, ctx_id, "delete_failed")
            _update_progress(
                "FAILED",
                {
                    "stage": "error",
                    "message": f"Qdrant deletion failed: {qdrant_exc}",
                    "task_id": task_id,
                },
            )
            raise

        # ── Step 3: Delete DB row (ONLY after S3 + Qdrant succeed) ────────
        _update_progress(
            "DELETING",
            {
                "stage": "deleting_db",
                "message": "Removing context record...",
                "tagged_s3_objects": tagged_s3,
                "deleted_qdrant_points": deleted_qdrant,
                "task_id": task_id,
            },
        )
        ctx_repo = ThirdPartyContextRepository(db)
        deleted_db = ctx_repo.delete(ctx_id)

        logger.info(
            "Delete task %s complete for agent %s (context %s).",
            task_id,
            agent_id,
            context_id,
        )
        return {
            "stage": "complete",
            "message": "Context deleted successfully (S3 data tagged for 30-day expiry).",
            "context_id": context_id,
            "agent_id": agent_id,
            "tagged_s3_objects": tagged_s3,
            "deleted_qdrant_points": deleted_qdrant,
            "deleted_db_row": deleted_db,
            "s3_retention_days": 30,
            "task_id": task_id,
        }

    except Exception as exc:
        logger.exception("Delete task %s failed: %s", task_id, exc)
        raise self.retry(exc=exc, countdown=60)

    finally:
        db.close()
