"""Unified agent activity service — logs + broadcasts all agent actions.

Every agent action (integration calls, task changes, cron runs, context syncs,
connections) flows through this service so the frontend gets a single real-time
stream per agent.

Usage from any service:
    from agent_manager.services.agent_activity_service import log_activity
    await log_activity(db, agent_id, "integration_call", "Called Slack /chat.postMessage (200, 142ms)", {...})
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from ..repositories.agent_activity_repository import AgentActivityRepository
from ..ws_manager import activity_ws_manager

logger = logging.getLogger("agent_manager.services.agent_activity_service")


async def log_activity(
    db: Session,
    agent_id: str,
    activity_type: str,
    summary: str,
    metadata: dict[str, Any] | None = None,
    status: str = "success",
) -> None:
    """Persist an activity record and broadcast it via WebSocket.

    This is the single entry point for all agent activity logging.
    Call it from any service after an action completes.
    """
    try:
        repo = AgentActivityRepository(db)
        activity = repo.create(
            agent_id=agent_id,
            activity_type=activity_type,
            summary=summary,
            metadata=metadata,
            status=status,
        )

        # Broadcast to connected clients
        event_data = {
            "id": str(activity.id),
            "agent_id": activity.agent_id,
            "activity_type": activity.activity_type,
            "summary": activity.summary,
            "metadata": activity.metadata_,
            "status": activity.status,
            "created_at": activity.created_at.isoformat(),
        }

        await activity_ws_manager.broadcast("agent_activity", event_data)
        logger.debug("Activity logged: agent=%s type=%s", agent_id, activity_type)
    except Exception:
        logger.exception("Failed to log activity: agent=%s type=%s", agent_id, activity_type)


def log_activity_sync(
    db: Session,
    agent_id: str,
    activity_type: str,
    summary: str,
    metadata: dict[str, Any] | None = None,
    status: str = "success",
) -> None:
    """Synchronous version for use in non-async contexts (Celery tasks, etc.).

    Persists to DB but does NOT broadcast via WebSocket (async-only).
    The frontend will pick up these events on next REST poll.
    """
    try:
        repo = AgentActivityRepository(db)
        repo.create(
            agent_id=agent_id,
            activity_type=activity_type,
            summary=summary,
            metadata=metadata,
            status=status,
        )
        logger.debug("Activity logged (sync): agent=%s type=%s", agent_id, activity_type)
    except Exception:
        logger.exception("Failed to log activity (sync): agent=%s type=%s", agent_id, activity_type)
