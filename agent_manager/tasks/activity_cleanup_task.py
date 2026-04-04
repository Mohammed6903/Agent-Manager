"""Daily cleanup task — deletes agent activity records older than 7 days."""
from __future__ import annotations

import logging

from agent_manager.celery_app import celery_app
from agent_manager.database import SessionLocal
from agent_manager.repositories.agent_activity_repository import AgentActivityRepository

logger = logging.getLogger(__name__)

RETENTION_DAYS = 7


@celery_app.task(bind=True, max_retries=0)
def cleanup_old_activities(self) -> dict:
    """Delete agent activities older than RETENTION_DAYS."""
    db = SessionLocal()
    try:
        repo = AgentActivityRepository(db)
        deleted = repo.delete_older_than(days=RETENTION_DAYS)
        logger.info("Activity cleanup: deleted %d records older than %d days", deleted, RETENTION_DAYS)
        return {"deleted": deleted, "retention_days": RETENTION_DAYS}
    finally:
        db.close()
