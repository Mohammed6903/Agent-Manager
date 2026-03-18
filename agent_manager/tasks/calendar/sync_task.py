"""Daily periodic synchronization tasks for Calendar."""
from __future__ import annotations
import logging
from agent_manager.celery_app import celery_app
from agent_manager.database import SessionLocal
from agent_manager.repositories.third_party_context_repository import ThirdPartyContextRepository
from agent_manager.tasks.generic_context_task import ingest_and_pipeline

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, max_retries=0)
def daily_calendar_sync(self) -> dict:
    """Kick off incremental sync for every active Calendar agent."""
    db = SessionLocal()
    try:
        contexts = ThirdPartyContextRepository(db).get_all_by_integration_and_status(
            integration_name="google_calendar", status="complete"
        )
        if not contexts:
            logger.info("Daily sync: no active Calendar agents.")
            return {"scheduled": 0}

        seen_agents = set()
        task_ids = []
        for ctx in contexts:
            if ctx.agent_id in seen_agents:
                continue
            seen_agents.add(ctx.agent_id)

            task = ingest_and_pipeline.apply_async(
                kwargs={
                    "agent_id":         str(ctx.agent_id),
                    "context_id":       str(ctx.id),
                    "force_full_sync":  False,
                    "is_daily_sync":    True,
                    "integration_name": "google_calendar",
                },
                queue="ingest",
                countdown=len(task_ids) * 15,
            )
            task_ids.append(task.id)
            logger.info("Daily calendar sync queued: agent=%s task=%s", ctx.agent_id, task.id)

        return {"scheduled": len(task_ids), "task_ids": task_ids}
    finally:
        db.close()
