"""Celery task — runs digest → chunk → embed → Qdrant for stored S3 emails."""
from __future__ import annotations

import logging

from celery.contrib.abortable import AbortableTask

from ..celery_app import celery_app
from ..database import SessionLocal
from ..services import s3_service, gmail_pipeline_service
from ..services.gmail_auth_service import get_valid_credentials
from .gmail_ingest_task import register_active_task, unregister_active_task

logger = logging.getLogger(__name__)


def _progress(self: AbortableTask, meta: dict) -> None:
    """Emit a PROCESSING state update with *meta* attached to ``task_id``."""
    self.update_state(
        state="PROCESSING",
        meta={**meta, "task_id": self.request.id},
    )


@celery_app.task(bind=True, base=AbortableTask, max_retries=3)
def pipeline_gmail(self, agent_id: str) -> dict:
    """Read raw emails from S3 → digest → chunk → embed → upsert to Qdrant."""
    task_id: str = self.request.id
    db = SessionLocal()
    try:
        register_active_task(agent_id, task_id)

        creds = get_valid_credentials(db, agent_id)
        if not creds:
            raise RuntimeError("No valid credentials for agent")

        from googleapiclient.discovery import build

        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        account_email = profile.get("emailAddress", "")

        message_ids = s3_service.list_gmail_message_ids(agent_id)
        total = len(message_ids)

        _progress(self, {
            "stage": "processing",
            "message": "Starting pipeline...",
            "processed": 0,
            "total": total,
            "failed": 0,
        })

        processed = failed = 0

        for msg_id in message_ids:
            if self.is_aborted():
                logger.info("Pipeline task %s aborted at %d/%d.", task_id, processed, total)
                return {
                    "stage": "aborted",
                    "message": "Task was cancelled.",
                    "processed": processed,
                    "total": total,
                    "failed": failed,
                    "task_id": task_id,
                }

            raw = s3_service.load_gmail_raw(agent_id, msg_id)
            if not raw:
                failed += 1
            else:
                try:
                    gmail_pipeline_service.process_message(raw, agent_id, account_email)
                    processed += 1
                except Exception:
                    failed += 1
                    logger.exception(
                        "Pipeline failed for message %s (agent %s).", msg_id, agent_id
                    )

            _progress(self, {
                "stage": "processing",
                "message": "Processing emails...",
                "processed": processed,
                "total": total,
                "failed": failed,
            })

        return {
            "stage": "complete",
            "message": "Pipeline complete.",
            "processed": processed,
            "total": total,
            "failed": failed,
            "task_id": task_id,
        }

    except Exception as exc:
        self.update_state(
            state="FAILURE",
            meta={"stage": "error", "message": str(exc), "task_id": task_id},
        )
        raise self.retry(exc=exc, countdown=300)
    finally:
        unregister_active_task(agent_id, task_id)
        db.close()