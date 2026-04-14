"""Agent Activity REST endpoints — history and WebSocket stream.

Heartbeats are emitted server-side every 5 seconds by heartbeat_service.py
(launched in app lifespan). No client polling needed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..repositories.agent_activity_repository import AgentActivityRepository

router = APIRouter(tags=["Agent Activity"])


def _parse_iso(name: str, value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        # Accepts 2026-04-14, 2026-04-14T10:00:00Z, 2026-04-14T10:00:00+00:00, etc.
        # Python's fromisoformat handles the last two directly; the trailing
        # Z needs a tiny fixup.
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as err:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {name} datetime: {value!r} (use ISO 8601)",
        ) from err


@router.get("/agents/{agent_id}/activity")
def get_agent_activity(
    agent_id: str,
    limit: int = Query(50, ge=1, le=200),
    activity_type: Optional[str] = Query(None, description="Filter by type"),
    user_id: Optional[str] = Query(
        None,
        description="Scope to a single user's activity. Omit for all-users view (founder).",
    ),
    from_: Optional[str] = Query(
        None,
        alias="from",
        description="ISO 8601 start of range (inclusive). e.g. 2026-04-12T00:00:00Z",
    ),
    to: Optional[str] = Query(
        None,
        description="ISO 8601 end of range (inclusive). e.g. 2026-04-14T23:59:59Z",
    ),
    db: Session = Depends(get_db),
):
    """Get activity for an agent.

    - `from` / `to` narrow the time window (defaults: no filter).
    - `user_id` narrows to a single actor; injected by roam-backend for
      employees so they only see their own rows. Omit for founder view.
    - `limit` caps results — if the range is wider than the limit you'll
      see only the most recent `limit` rows within it.
    """
    repo = AgentActivityRepository(db)
    activities = repo.list_recent(
        agent_id,
        limit=limit,
        activity_type=activity_type,
        user_id=user_id,
        from_time=_parse_iso("from", from_),
        to_time=_parse_iso("to", to),
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
