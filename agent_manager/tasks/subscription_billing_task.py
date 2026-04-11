"""Celery task — daily subscription renewal processing."""

from __future__ import annotations

import asyncio
import logging

from agent_manager.celery_app import celery_app
from agent_manager.config import settings
from agent_manager.database import SessionLocal
from agent_manager.services.subscription_service import SubscriptionService

logger = logging.getLogger("agent_manager.tasks.subscription_billing_task")


@celery_app.task(bind=True, max_retries=2)
def process_subscription_renewals(self):
    """Run daily: renew active subscriptions, lock failed ones, soft-delete stale locks.

    No-op when ``settings.ENFORCE_AGENT_SUBSCRIPTION`` is False. The beat
    schedule still fires this task daily, but with the flag off it logs
    a skip message and returns immediately — no wallet deductions, no
    agent locks. Flip the flag to re-enable monthly billing.
    """
    if not settings.ENFORCE_AGENT_SUBSCRIPTION:
        logger.info(
            "Subscription renewal task skipped: ENFORCE_AGENT_SUBSCRIPTION=False "
            "(pay-as-you-go mode — no monthly $24 charges, no agent locking)."
        )
        return {"skipped": True, "reason": "enforcement_disabled"}

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
