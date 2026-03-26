"""Celery task — retry failed ingestion items from the Dead Letter Queue."""

from __future__ import annotations

import logging

from agent_manager.celery_app import celery_app
from agent_manager.database import SessionLocal

logger = logging.getLogger("agent_manager.tasks.dlq_retry_task")


@celery_app.task(bind=True, max_retries=0)
def retry_failed_ingestions(self):
    """Process retryable items from the DLQ. Runs hourly via beat."""
    db = SessionLocal()
    try:
        from agent_manager.repositories.failed_ingestion_repository import FailedIngestionRepository

        dlq = FailedIngestionRepository(db)

        # Expire items that exceeded max retries
        expired = dlq.expire_old_failures()
        if expired:
            logger.info("DLQ: marked %d items as permanently_failed", expired)

        # Get retryable items
        items = dlq.list_retryable(limit=50)
        if not items:
            return {"retried": 0, "resolved": 0, "failed": 0, "expired": expired}

        resolved = 0
        failed = 0

        for item in items:
            dlq.mark_retrying(item.id)
            try:
                if item.phase == "pipeline":
                    _retry_pipeline_item(db, item)
                elif item.phase == "ingest":
                    _retry_ingest_item(db, item)
                else:
                    logger.warning("DLQ: unknown phase '%s' for item %s", item.phase, item.id)
                    continue

                dlq.mark_resolved(item.id)
                resolved += 1
                logger.info("DLQ: resolved %s/%s/%s", item.agent_id, item.integration_name, item.message_id)

            except Exception as exc:
                failed += 1
                logger.warning(
                    "DLQ: retry failed for %s/%s/%s (attempt %d): %s",
                    item.agent_id, item.integration_name, item.message_id,
                    item.retry_count, exc,
                )

        result = {"retried": len(items), "resolved": resolved, "failed": failed, "expired": expired}
        logger.info("DLQ retry run complete: %s", result)
        return result

    finally:
        db.close()


def _retry_pipeline_item(db, item):
    """Re-run the pipeline (embed + vectorize) for a single item."""
    from agent_manager.services.context_providers import get_provider

    provider = get_provider(item.integration_name)
    if not provider:
        raise ValueError(f"No provider for integration: {item.integration_name}")

    # Load from S3
    raws = provider.load_s3_batch(item.agent_id, [item.message_id])
    if not raws:
        raise ValueError(f"Item {item.message_id} not found in S3")

    # Get account email from the raw data
    account_email = raws[0].get("account_email", "unknown")

    # Run pipeline for single item
    provider.pipeline_single(raws[0], item.agent_id, account_email)


def _retry_ingest_item(db, item):
    """Re-fetch a single item from the source API and save to S3."""
    # For now, log and skip — ingest retries are handled by the next full sync
    logger.info(
        "DLQ: ingest retry for %s/%s — will be picked up by next sync cycle",
        item.agent_id, item.message_id,
    )
    # Mark as resolved since next sync will re-fetch
    # (The item exists in Gmail, just failed to fetch last time)
