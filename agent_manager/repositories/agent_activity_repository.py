"""Repository for AgentActivity CRUD and cleanup."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, delete as sa_delete
from sqlalchemy.orm import Session

from ..models.agent_activity import AgentActivity


class AgentActivityRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        agent_id: str,
        activity_type: str,
        summary: str,
        metadata: dict | None = None,
        status: str = "success",
    ) -> AgentActivity:
        activity = AgentActivity(
            agent_id=agent_id,
            activity_type=activity_type,
            summary=summary,
            metadata_=metadata,
            status=status,
        )
        self.db.add(activity)
        self.db.commit()
        self.db.refresh(activity)
        return activity

    def list_recent(
        self,
        agent_id: str,
        limit: int = 50,
        activity_type: Optional[str] = None,
    ) -> list[AgentActivity]:
        stmt = (
            select(AgentActivity)
            .where(AgentActivity.agent_id == agent_id)
            .order_by(AgentActivity.created_at.desc())
            .limit(limit)
        )
        if activity_type:
            stmt = stmt.where(AgentActivity.activity_type == activity_type)
        return list(self.db.execute(stmt).scalars().all())

    def delete_older_than(self, days: int = 30) -> int:
        """Delete activities older than N days. Returns count deleted."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = self.db.execute(
            sa_delete(AgentActivity).where(AgentActivity.created_at < cutoff)
        )
        self.db.commit()
        return result.rowcount

    def delete_for_agent(self, agent_id: str) -> int:
        """Delete all activities for an agent."""
        result = self.db.execute(
            sa_delete(AgentActivity).where(AgentActivity.agent_id == agent_id)
        )
        self.db.commit()
        return result.rowcount
