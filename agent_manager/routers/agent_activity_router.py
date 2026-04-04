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
    db: Session = Depends(get_db),
):
    """Get recent activity for an agent (last 7 days, most recent first)."""
    repo = AgentActivityRepository(db)
    activities = repo.list_recent(agent_id, limit=limit, activity_type=activity_type)
    return [
        {
            "id": str(a.id),
            "agent_id": a.agent_id,
            "activity_type": a.activity_type,
            "summary": a.summary,
            "metadata": a.metadata_,
            "status": a.status,
            "created_at": a.created_at.isoformat(),
        }
        for a in activities
    ]
