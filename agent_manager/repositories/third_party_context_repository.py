"""Repository for ThirdPartyContext CRUD operations."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.third_party_context import ThirdPartyContext


class ThirdPartyContextRepository:
    """Data access layer for the third_party_contexts table."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        agent_id: str,
        integration_name: str,
        metadata: dict | None = None,
    ) -> ThirdPartyContext:
        """Insert a new context row with status 'pending'."""
        row = ThirdPartyContext(
            agent_id=agent_id,
            integration_name=integration_name,
            integration_metadata=metadata,
            status="pending",
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_task(
        self,
        context_id: uuid.UUID,
        celery_task_id: str,
        status: str,
    ) -> Optional[ThirdPartyContext]:
        """Attach a Celery task ID and update status atomically."""
        row = self.get(context_id)
        if not row:
            return None
        row.celery_task_id = celery_task_id
        row.status = status
        row.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_status(
        self, context_id: uuid.UUID, status: str
    ) -> Optional[ThirdPartyContext]:
        """Update the status column only."""
        row = self.get(context_id)
        if not row:
            return None
        row.status = status
        row.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get(self, context_id: uuid.UUID) -> Optional[ThirdPartyContext]:
        """Fetch a single row by primary key."""
        return self.db.execute(
            select(ThirdPartyContext).where(ThirdPartyContext.id == context_id)
        ).scalar_one_or_none()

    def get_by_agent(self, agent_id: str) -> list[ThirdPartyContext]:
        """Return all context rows for a given agent, newest first."""
        return list(
            self.db.execute(
                select(ThirdPartyContext)
                .where(ThirdPartyContext.agent_id == agent_id)
                .order_by(ThirdPartyContext.created_at.desc())
            )
            .scalars()
            .all()
        )

    def get_all_complete(self) -> list[ThirdPartyContext]:
        """Return all ThirdPartyContext rows with status 'complete'."""
        return list(
            self.db.execute(
                select(ThirdPartyContext)
                .where(ThirdPartyContext.status == "complete")
                .order_by(ThirdPartyContext.created_at.desc())
            )
            .scalars()
            .all()
        )

    def get_active_by_agent_and_integration(
        self, agent_id: str, integration_name: str
    ) -> Optional[ThirdPartyContext]:
        """Return the newest active context row for agent + integration.

        Active rows are those still in-flight and not terminal.
        """
        active_statuses = ("pending", "ingesting", "processing")
        return self.db.execute(
            select(ThirdPartyContext)
            .where(
                ThirdPartyContext.agent_id == agent_id,
                ThirdPartyContext.integration_name == integration_name,
                ThirdPartyContext.status.in_(active_statuses),
            )
            .order_by(ThirdPartyContext.created_at.desc())
        ).scalar_one_or_none()

    def delete(self, context_id: uuid.UUID) -> bool:
        """Delete a context row by ID.

        Returns True when the row existed and was deleted.
        """
        row = self.get(context_id)
        if not row:
            return False
        self.db.delete(row)
        self.db.commit()
        return True
