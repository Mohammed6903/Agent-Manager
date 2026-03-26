"""Celery application instance."""
from __future__ import annotations

from celery import Celery

from .config import settings

celery_app = Celery(
    "openclaw",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        # Generic task (used by all integrations)
        "agent_manager.tasks.generic_context_task",
        # Per-integration ingest helpers (full_sync, incremental_sync, etc.)
        "agent_manager.tasks.gmail.ingest_task",
        "agent_manager.tasks.calendar.ingest_task",
        "agent_manager.tasks.docs.ingest_task",
        "agent_manager.tasks.sheets.ingest_task",
        # Daily sync schedulers
        "agent_manager.tasks.gmail.sync_task",
        "agent_manager.tasks.calendar.sync_task",
        "agent_manager.tasks.docs.sync_task",
        "agent_manager.tasks.sheets.sync_task",
        # Dead Letter Queue retry
        "agent_manager.tasks.dlq_retry_task",
    ],
)

from kombu import Queue
from celery.schedules import crontab

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Ensure tasks are re-queued if the worker crashes mid-execution
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # User-requested production settings
    task_track_started=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    broker_connection_retry_on_startup=True,

    # Priority queues
    task_queues=[
        Queue("default", routing_key="default"),
        Queue("ingest", routing_key="ingest"),
        Queue("beat", routing_key="beat"),
    ],
    task_default_queue="default",
    task_routes={
        "agent_manager.tasks.generic_context_task.ingest_and_pipeline": {"queue": "ingest"},
        "agent_manager.tasks.generic_context_task.delete_context_data": {"queue": "ingest"},
        "agent_manager.tasks.gmail.sync_task.daily_gmail_sync":         {"queue": "beat"},
        "agent_manager.tasks.calendar.sync_task.daily_calendar_sync":   {"queue": "beat"},
        "agent_manager.tasks.docs.sync_task.daily_docs_sync":           {"queue": "beat"},
        "agent_manager.tasks.sheets.sync_task.daily_sheets_sync":       {"queue": "beat"},
        "agent_manager.tasks.dlq_retry_task.retry_failed_ingestions": {"queue": "beat"},
    },

    # Beat configuration
    beat_schedule={
        "daily-gmail-sync": {
            "task": "agent_manager.tasks.gmail.sync_task.daily_gmail_sync",
            "schedule": crontab(hour=2, minute=0),  # 2 AM UTC daily
            "options": {"queue": "beat"},
        },
        "daily-calendar-sync": {
            "task": "agent_manager.tasks.calendar.sync_task.daily_calendar_sync",
            "schedule": crontab(hour=2, minute=30),  # 2:30 AM UTC daily
            "options": {"queue": "beat"},
        },
        "daily-docs-sync": {
            "task": "agent_manager.tasks.docs.sync_task.daily_docs_sync",
            "schedule": crontab(hour=3, minute=0),  # 3 AM UTC daily
            "options": {"queue": "beat"},
        },
        "daily-sheets-sync": {
            "task": "agent_manager.tasks.sheets.sync_task.daily_sheets_sync",
            "schedule": crontab(hour=3, minute=30),  # 3:30 AM UTC daily
            "options": {"queue": "beat"},
        },
        "hourly-dlq-retry": {
            "task": "agent_manager.tasks.dlq_retry_task.retry_failed_ingestions",
            "schedule": crontab(minute=15),  # Every hour at :15
            "options": {"queue": "beat"},
        },
    },
    beat_scheduler="celery.beat:PersistentScheduler",
    beat_schedule_filename="/tmp/celerybeat-schedule",
)
