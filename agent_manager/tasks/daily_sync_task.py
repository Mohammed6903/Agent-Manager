"""Daily periodic synchronization tasks."""
from __future__ import annotations
import logging
from ..celery_app import celery_app
from ..database import SessionLocal
from ..repositories.third_party_context_repository import ThirdPartyContextRepository
from .gmail_context_task import ingest_and_pipeline_gmail

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, max_retries=0)
def daily_gmail_sync(self) -> dict:
    """Kick off incremental sync for every active Gmail agent."""
    db = SessionLocal()
    try:
        # We only want to sync agents who have a completed initial ingest.
        contexts = ThirdPartyContextRepository(db).get_all_by_integration_and_status(
            integration_name="gmail", status="complete"
        )
        if not contexts:
            logger.info("Daily sync: no active Gmail agents.")
            return {"scheduled": 0}

        # Dedup by agent_id — if an agent has multiple complete contexts, only sync the newest one.
        seen_agents = set()
        task_ids = []
        for ctx in contexts:
            if ctx.agent_id in seen_agents:
                continue
            seen_agents.add(ctx.agent_id)

            task = ingest_and_pipeline_gmail.apply_async(
                kwargs={
                    "agent_id":        str(ctx.agent_id),
                    "context_id":      str(ctx.id),
                    "force_full_sync": False,
                },
                queue="ingest",
                countdown=len(task_ids) * 15,  # stagger 15s apart — thundering herd prevention
            )
            task_ids.append(task.id)
            logger.info("Daily sync queued: agent=%s task=%s", ctx.agent_id, task.id)

        return {"scheduled": len(task_ids), "task_ids": task_ids}
    finally:
        db.close()
