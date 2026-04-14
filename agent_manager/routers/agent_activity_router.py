"""Agent Activity REST endpoints — history and WebSocket stream.

Heartbeats are emitted server-side every 5 seconds by heartbeat_service.py
(launched in app lifespan). No client polling needed.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..repositories.agent_activity_repository import AgentActivityRepository

router = APIRouter(tags=["Agent Activity"])


@router.get("/agents/{agent_id}/activity")
def get_agent_activity(
    agent_id: str,
    limit: int = Query(50, ge=1, le=200),
    activity_type: Optional[str] = Query(None, description="Filter by type"),
    user_id: Optional[str] = Query(
        None,
        description="Scope to a single user's activity. Omit for all-users view (founder).",
    ),
    db: Session = Depends(get_db),
):
    """Get recent activity for an agent.

    `user_id` narrows the feed to a single actor — roam-backend injects
    it for employees (their own userId) and omits it for founders
    (full view). System-generated rows (user_id NULL) are excluded when
    a filter is provided; included when it isn't.
    """
    repo = AgentActivityRepository(db)
    activities = repo.list_recent(
        agent_id,
        limit=limit,
        activity_type=activity_type,
        user_id=user_id,
    )
    return [
        {
            "id": str(a.id),
            "agent_id": a.agent_id,
            "user_id": a.user_id,
            "activity_type": a.activity_type,
            "summary": a.summary,
            "metadata": a.metadata_,
            "status": a.status,
            "created_at": a.created_at.isoformat(),
        }
        for a in activities
    ]
