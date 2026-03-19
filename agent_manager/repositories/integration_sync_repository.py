"""Generic repository for integration sync state."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from agent_manager.models.gmail import IntegrationSyncState


class IntegrationSyncRepository:
    """Manages persistence of per-agent, per-integration sync state.

    Replaces GmailSyncRepository and CalendarSyncRepository with a single
    implementation that works for any integration.
    """

    def __init__(self, db: Session, integration_name: str) -> None:
        self.db = db
        self.integration_name = integration_name

    def get(self, agent_id: str) -> IntegrationSyncState | None:
        """Return the sync state for *agent_id* and this integration, or None."""
        return self.db.execute(
            select(IntegrationSyncState).where(
                and_(
                    IntegrationSyncState.agent_id == agent_id,
                    IntegrationSyncState.integration_name == self.integration_name,
                )
            )
        ).scalar_one_or_none()

    def save_cursor(
        self, agent_id: str, cursor: str, fetched_count: int = 0,
    ) -> IntegrationSyncState:
        """Create or update sync state after a successful sync.

        ``cursor`` is opaque — historyId for Gmail, nextSyncToken for Calendar, etc.
        """
        state = self.get(agent_id)
        if state:
            state.sync_cursor = cursor
            state.last_synced_at = datetime.now(timezone.utc)
            state.total_fetched += fetched_count
        else:
            state = IntegrationSyncState(
                agent_id=agent_id,
                integration_name=self.integration_name,
                sync_cursor=cursor,
                last_synced_at=datetime.now(timezone.utc),
                total_fetched=fetched_count,
            )
            self.db.add(state)

        try:
            self.db.commit()
            self.db.refresh(state)
        except Exception:
            self.db.rollback()
            state = self.db.merge(
                IntegrationSyncState(
                    agent_id=agent_id,
                    integration_name=self.integration_name,
                    sync_cursor=cursor,
                    last_synced_at=datetime.now(timezone.utc),
                    total_fetched=fetched_count,
                )
            )
            self.db.commit()

        return state

    def clear(self, agent_id: str) -> None:
        """Reset sync state — forces a full re-fetch on next run."""
        state = self.get(agent_id)
        if state:
            self.db.delete(state)
            self.db.commit()
