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
        "agent_manager.tasks.gmail_ingest_task",
        "agent_manager.tasks.daily_sync_task",
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
        "agent_manager.tasks.gmail_context_task.ingest_and_pipeline_gmail": {"queue": "ingest"},
        "agent_manager.tasks.gmail_context_task.delete_gmail_context":      {"queue": "ingest"},
        "agent_manager.tasks.daily_sync_task.daily_gmail_sync":             {"queue": "beat"},
    },
    
    # Beat configuration
    beat_schedule={
        "daily-gmail-sync": {
            "task": "agent_manager.tasks.daily_sync_task.daily_gmail_sync",
            "schedule": crontab(hour=2, minute=0),  # 2 AM UTC daily
            "options": {"queue": "beat"},
        },
    },
    beat_scheduler="celery.beat:PersistentScheduler",
    beat_schedule_filename="/tmp/celerybeat-schedule",
)