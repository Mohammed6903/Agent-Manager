"""Celery application instance."""
from __future__ import annotations

from celery import Celery

from .config import settings

celery_app = Celery(
    "openclaw",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "agent_manager.tasks.gmail_context_task",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Ensure tasks are re-queued if the worker crashes mid-execution
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)