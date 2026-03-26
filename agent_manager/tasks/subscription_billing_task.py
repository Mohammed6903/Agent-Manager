"""Celery task — daily subscription renewal processing."""

from __future__ import annotations

import asyncio
import logging

from agent_manager.celery_app import celery_app
from agent_manager.database import SessionLocal
from agent_manager.services.subscription_service import SubscriptionService

logger = logging.getLogger("agent_manager.tasks.subscription_billing_task")


@celery_app.task(bind=True, max_retries=2)
def process_subscription_renewals(self):
    """Run daily: renew active subscriptions, lock failed ones, soft-delete stale locks."""
    db = SessionLocal()
    try:
        svc = SubscriptionService(db)
        result = asyncio.run(svc.process_renewals())
        logger.info("Subscription renewal task complete: %s", result)
        return result
    except Exception as exc:
        logger.error("Subscription renewal task failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)
    finally:
        db.close()
