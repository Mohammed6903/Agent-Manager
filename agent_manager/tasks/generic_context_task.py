"""Generic Celery tasks — unified ingest + pipeline and delete for any integration."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from celery import current_task
from celery.contrib.abortable import AbortableTask
from googleapiclient.errors import HttpError

from agent_manager.celery_app import celery_app
from agent_manager.database import SessionLocal
from agent_manager.repositories.integration_sync_repository import IntegrationSyncRepository
from agent_manager.repositories.third_party_context_repository import ThirdPartyContextRepository
from agent_manager.services import qdrant_service
from agent_manager.integrations.google.gmail.auth_service import get_valid_credentials

logger = logging.getLogger(__name__)

_PIPELINE_BATCH_SIZE = 200

# ── Active-task Registry ──────────────────────────────────────────────────────
# Shared with the per-integration ingest_task modules (they use the same Redis hash).

import redis as redis_lib
from agent_manager.config import settings

_ACTIVE_KEY = "openclaw:ingest:active"
_ACTIVE_TTL = 86_400


def _redis() -> redis_lib.Redis:
    return redis_lib.from_url(settings.REDIS_URL, decode_responses=True)


def _active_field(integration: str, agent_id: str, task_type: str) -> str:
    return f"{integration}:{task_type}:{agent_id}"


def register_active_task(integration: str, agent_id: str, task_id: str, task_type: str = "ingest") -> None:
    r = _redis()
    r.hset(_ACTIVE_KEY, _active_field(integration, agent_id, task_type), task_id)
    r.expire(_ACTIVE_KEY, _ACTIVE_TTL)


def unregister_active_task(integration: str, agent_id: str, task_id: str, task_type: str = "ingest") -> None:
    field = _active_field(integration, agent_id, task_type)
    r = _redis()
    current = r.hget(_ACTIVE_KEY, field)
    if current == task_id:
        r.hdel(_ACTIVE_KEY, field)


from agent_manager.tasks._progress_helper import (
    set_progress_context,
    update_progress as _update_progress,
)


def _set_ctx_status(db: Any, ctx_id: uuid.UUID, status: str) -> None:
    try:
        ThirdPartyContextRepository(db).update_status(ctx_id, status)
    except Exception:
        logger.exception("Failed to update ThirdPartyContext %s → %s.", ctx_id, status)


# ── Generic Ingest + Pipeline ────────────────────────────────────────────────


@celery_app.task(bind=True, base=AbortableTask, max_retries=3)
def ingest_and_pipeline(
    self,
    agent_id: str,
    context_id: str,
    force_full_sync: bool = False,
    is_daily_sync: bool = False,
    integration_name: str = "gmail",
) -> dict[str, object]:
    """Ingest data to S3, then run the embedding pipeline to Qdrant.

    Works for any registered integration — the provider supplies all
    integration-specific hooks (sync, parse, pipeline, S3 layout).
    """
    from agent_manager.services.context_providers import get_provider

    task_id: str = self.request.id
    ctx_id = uuid.UUID(context_id)
    db = SessionLocal()
    set_progress_context(agent_id, task_id)

    provider = get_provider(integration_name)
    if not provider:
        raise RuntimeError(f"Unknown integration: {integration_name}")

    try:
        register_active_task(integration_name, agent_id, task_id, task_type="ingest")
        ctx_repo = ThirdPartyContextRepository(db)
        sync_repo = IntegrationSyncRepository(db, integration_name)

        if not is_daily_sync:
            ctx_repo.update_task(ctx_id, task_id, "ingesting")
        else:
            ctx_repo.update_celery_task_id(ctx_id, task_id)

        if force_full_sync:
            logger.info("force_full_sync=True: clearing sync state for agent %s (%s).", agent_id, integration_name)
            sync_repo.clear(agent_id)

        # ── Phase 1: Ingest ───────────────────────────────────────────────
        _update_progress(
            "FETCHING",
            {
                "stage": "starting",
                "message": f"Starting {provider.display_name} fetch...",
                "current": 0,
                "total": 0,
                "percentage": 0,
                "skipped": 0,
                "failed": 0,
                "task_id": task_id,
            },
        )

        creds = get_valid_credentials(db, agent_id)
        if not creds:
            raise RuntimeError(f"{provider.display_name} service unavailable — check OAuth credentials")

        api_service = provider.build_api_service(creds)
        account_email: str = provider.get_account_email(api_service)

        _captured_task_id = task_id
        is_aborted = lambda: self.is_aborted(task_id=_captured_task_id)  # noqa: E731

        counters: dict[str, int] = {"fetched": 0, "skipped": 0, "failed": 0}
        sync_state = sync_repo.get(agent_id)
        new_cursor: str | None

        if sync_state and sync_state.sync_cursor:
            _update_progress(
                "FETCHING",
                {
                    "stage": "fetching",
                    "message": f"Fetching new {provider.display_name} data since last sync...",
                    "current": 0,
                    "total": 0,
                    "percentage": 0,
                    "skipped": 0,
                    "failed": 0,
                    "task_id": task_id,
                },
            )
            try:
                new_cursor = provider.incremental_sync(
                    api_service, agent_id, sync_state.sync_cursor, counters, is_aborted,
                )
            except HttpError as exc:
                if exc.status_code == provider.expired_sync_cursor_http_code:
                    logger.warning(
                        "Sync cursor expired for agent_id=%s (%s), falling back to full sync.",
                        agent_id, integration_name,
                    )
                    sync_repo.clear(agent_id)
                    counters = {"fetched": 0, "skipped": 0, "failed": 0}
                    _update_progress(
                        "FETCHING",
                        {
                            "stage": "fetching",
                            "message": f"Starting full {provider.display_name} fetch...",
                            "current": 0,
                            "total": 0,
                            "percentage": 0,
                            "skipped": 0,
                            "failed": 0,
                            "task_id": task_id,
                        },
                    )
                    new_cursor = provider.full_sync(
                        api_service, agent_id, counters, is_aborted,
                    )
                else:
                    raise
        else:
            _update_progress(
                "FETCHING",
                {
                    "stage": "fetching",
                    "message": f"Starting full {provider.display_name} fetch...",
                    "current": 0,
                    "total": 0,
                    "percentage": 0,
                    "skipped": 0,
                    "failed": 0,
                    "task_id": task_id,
                },
            )
            new_cursor = provider.full_sync(
                api_service, agent_id, counters, is_aborted,
            )

        # Cancelled mid-ingest
        if new_cursor is None:
            _set_ctx_status(db, ctx_id, "cancelled")
            _update_progress(
                "TASK_CANCELLED",
                {
                    "stage": "cancelled",
                    "message": "Ingestion cancelled.",
                    "task_id": task_id,
                    **counters,
                },
            )
            return {"stage": "cancelled", "message": "Ingestion cancelled.", "task_id": task_id, **counters}

        # NOTE: cursor is saved AFTER pipeline completes (not here) to prevent
        # data loss if pipeline crashes — see end of Phase 2.
        ingest_result = dict(counters)

        # ── Phase 2: Pipeline ─────────────────────────────────────────────
        ctx_repo.update_status(ctx_id, "processing")

        item_ids = provider.list_s3_item_ids(agent_id)
        total_pipeline = len(item_ids)
        processed = failed = 0

        _update_progress(
            "PROCESSING",
            {
                "stage": "processing",
                "message": "Starting pipeline...",
                "current": 0,
                "total": total_pipeline,
                "percentage": 0,
                "failed": 0,
                "task_id": task_id,
            },
        )

        for i in range(0, len(item_ids), _PIPELINE_BATCH_SIZE):
            if is_aborted():
                _set_ctx_status(db, ctx_id, "cancelled")
                return {
                    "stage": "aborted",
                    "message": "Task was cancelled.",
                    "current": processed,
                    "total": total_pipeline,
                    "percentage": int((processed / total_pipeline * 100) if total_pipeline else 0),
                    "failed": failed,
                    "task_id": task_id,
                }

            batch_ids = item_ids[i : i + _PIPELINE_BATCH_SIZE]
            raws = provider.load_s3_batch(agent_id, batch_ids)
            s3_misses = len(batch_ids) - len(raws)
            failed += s3_misses
            try:
                provider.pipeline_batch(raws, agent_id, account_email)
                processed += len(raws)
            except Exception:
                logger.exception(
                    "Pipeline batch failed for agent %s (batch starting at %d), retrying individually...",
                    agent_id, i,
                )
                from ..repositories.failed_ingestion_repository import FailedIngestionRepository
                dlq = FailedIngestionRepository(db)
                for raw in raws:
                    try:
                        provider.pipeline_single(raw, agent_id, account_email)
                        processed += 1
                    except Exception as item_exc:
                        failed += 1
                        logger.exception("Single item failed: %s", raw.get("id"))
                        dlq.add(
                            agent_id=agent_id,
                            integration_name=integration_name,
                            message_id=str(raw.get("id", "")),
                            phase="pipeline",
                            error=str(item_exc),
                        )

            percentage = int((processed / total_pipeline * 100) if total_pipeline else 0)
            _update_progress(
                "PROCESSING",
                {
                    "stage": "processing",
                    "message": f"Processing ({processed}/{total_pipeline})...",
                    "current": processed,
                    "total": total_pipeline,
                    "percentage": percentage,
                    "failed": failed,
                    "task_id": task_id,
                },
            )

        # Save cursor only AFTER both ingest AND pipeline succeed.
        # This ensures failed pipeline runs will re-process those emails on next sync.
        if new_cursor:
            sync_repo.save_cursor(agent_id, new_cursor, fetched_count=counters["fetched"])
            logger.info(
                "Cursor saved for agent %s after successful pipeline (fetched=%d, processed=%d, failed=%d)",
                agent_id, counters["fetched"], processed, failed,
            )

        ctx_repo.update_status(ctx_id, "complete")

        from agent_manager.services.agent_activity_service import log_activity_sync
        log_activity_sync(db, agent_id, "context_sync_complete",
            f"Context sync complete: {integration_name} ({counters['fetched']} fetched, {processed} processed)",
            metadata={"integration": integration_name, "fetched": counters["fetched"], "processed": processed, "failed": failed},
            status="success")

        return {
            "stage": "complete",
            "message": "Ingest and pipeline complete.",
            "ingest": ingest_result,
            "current": processed,
            "total": total_pipeline,
            "percentage": 100,
            "failed": failed,
            "task_id": task_id,
        }

    except Exception as exc:
        if not is_daily_sync:
            _set_ctx_status(db, ctx_id, "failed")

        from agent_manager.services.agent_activity_service import log_activity_sync
        log_activity_sync(db, agent_id, "context_sync_failed",
            f"Context sync failed: {integration_name} — {str(exc)[:200]}",
            metadata={"integration": integration_name, "error": str(exc)[:500]},
            status="error")
        _update_progress(
            "TASK_ERROR",
            {"stage": "error", "message": str(exc), "task_id": task_id},
        )
        raise self.retry(exc=exc, countdown=300)

    finally:
        unregister_active_task(integration_name, agent_id, task_id, task_type="ingest")
        db.close()


# ── Generic Delete ───────────────────────────────────────────────────────────


@celery_app.task(bind=True, base=AbortableTask, max_retries=3)
def delete_context_data(
    self,
    agent_id: str,
    context_id: str,
    integration_name: str = "gmail",
) -> dict[str, object]:
    """Delete all data for a context (S3, Qdrant, DB) for any integration."""
    from agent_manager.services.context_providers import get_provider

    task_id: str = self.request.id
    ctx_id = uuid.UUID(context_id)
    db = SessionLocal()
    set_progress_context(agent_id, task_id)

    provider = get_provider(integration_name)
    if not provider:
        raise RuntimeError(f"Unknown integration: {integration_name}")

    try:
        register_active_task(integration_name, agent_id, task_id, task_type="delete")

        # ── Step 1: Delete S3 data ────────────────────────────────────────
        _update_progress(
            "DELETING",
            {
                "stage": "deleting_s3",
                "message": f"Deleting {provider.display_name} data from storage...",
                "current": 0,
                "total": 0,
                "percentage": 0,
                "task_id": task_id,
            },
        )
        try:
            deleted_s3 = provider.delete_s3_data(agent_id, task_id, _update_progress)
            logger.info(
                "Deleted/tagged %d S3 objects for agent %s (context %s).",
                deleted_s3, agent_id, context_id,
            )
        except Exception as s3_exc:
            logger.exception("S3 deletion failed for agent %s.", agent_id)
            _set_ctx_status(db, ctx_id, "delete_failed")
            _update_progress(
                "TASK_ERROR",
                {"stage": "error", "message": f"S3 deletion failed: {s3_exc}", "task_id": task_id},
            )
            raise

        # ── Step 2: Delete Qdrant vectors ─────────────────────────────────
        _update_progress(
            "DELETING",
            {
                "stage": "deleting_qdrant",
                "message": "Deleting vector embeddings from Qdrant...",
                "current": 0,
                "total": 1,
                "percentage": 0,
                "task_id": task_id,
            },
        )
        try:
            deleted_qdrant = qdrant_service.delete_points_for_agent_source(
                agent_id, provider.qdrant_source,
            )
            logger.info(
                "Deleted %d Qdrant points for agent %s (context %s).",
                deleted_qdrant, agent_id, context_id,
            )
        except Exception as qdrant_exc:
            logger.exception("Qdrant deletion failed for agent %s.", agent_id)
            _set_ctx_status(db, ctx_id, "delete_failed")
            _update_progress(
                "TASK_ERROR",
                {"stage": "error", "message": f"Qdrant deletion failed: {qdrant_exc}", "task_id": task_id},
            )
            raise

        # ── Step 3: Delete DB row ─────────────────────────────────────────
        _update_progress(
            "DELETING",
            {
                "stage": "deleting_db",
                "message": "Removing context record...",
                "current": 0,
                "total": 1,
                "percentage": 0,
                "task_id": task_id,
            },
        )
        ctx_repo = ThirdPartyContextRepository(db)
        ctx_repo.delete(ctx_id)

        sync_repo = IntegrationSyncRepository(db, integration_name)
        sync_repo.clear(agent_id)

        logger.info("Delete task %s complete for agent %s (context %s).", task_id, agent_id, context_id)
        return {
            "stage": "complete",
            "message": f"{provider.display_name} context deleted successfully.",
            "context_id": context_id,
            "agent_id": agent_id,
            "current": 1,
            "total": 1,
            "percentage": 100,
            "task_id": task_id,
        }

    except Exception as exc:
        logger.exception("Delete task %s failed: %s", task_id, exc)
        raise self.retry(exc=exc, countdown=60)

    finally:
        unregister_active_task(integration_name, agent_id, task_id, task_type="delete")
        db.close()
