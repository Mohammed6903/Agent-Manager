"""Repository for ThirdPartyContextAssignment CRUD operations."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.third_party_context import (
    ThirdPartyContext,
    ThirdPartyContextAssignment,
)


class ThirdPartyContextAssignmentRepository:
    """Data access layer for the third_party_context_assignments table."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def assign(self, context_id: uuid.UUID, agent_id: str) -> ThirdPartyContextAssignment:
        """Create an assignment. Returns existing row if already assigned."""
        existing = self.db.execute(
            select(ThirdPartyContextAssignment).where(
                ThirdPartyContextAssignment.context_id == context_id,
                ThirdPartyContextAssignment.agent_id == agent_id,
            )
        ).scalar_one_or_none()
        if existing:
            return existing

        row = ThirdPartyContextAssignment(
            context_id=context_id,
            agent_id=agent_id,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def unassign(self, context_id: uuid.UUID, agent_id: str) -> bool:
        """Delete an assignment. Returns True when the row existed."""
        row = self.db.execute(
            select(ThirdPartyContextAssignment).where(
                ThirdPartyContextAssignment.context_id == context_id,
                ThirdPartyContextAssignment.agent_id == agent_id,
            )
        ).scalar_one_or_none()
        if not row:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    def get_contexts_for_agent(
        self, agent_id: str, status: str | None = None
    ) -> list[ThirdPartyContext]:
        """Return ThirdPartyContext rows assigned to an agent.

        Args:
            agent_id: The agent to look up.
            status: Optional status filter (e.g. "complete").
        """
        stmt = (
            select(ThirdPartyContext)
            .join(
                ThirdPartyContextAssignment,
                ThirdPartyContextAssignment.context_id == ThirdPartyContext.id,
            )
            .where(ThirdPartyContextAssignment.agent_id == agent_id)
        )
        if status:
            stmt = stmt.where(ThirdPartyContext.status == status)
        return list(self.db.execute(stmt.order_by(ThirdPartyContext.created_at.desc())).scalars().all())

    def get_assignments_for_context(
        self, context_id: uuid.UUID
    ) -> list[ThirdPartyContextAssignment]:
        """Return all assignments for a given context."""
        return list(
            self.db.execute(
                select(ThirdPartyContextAssignment).where(
                    ThirdPartyContextAssignment.context_id == context_id,
                )
            )
            .scalars()
            .all()
        )
