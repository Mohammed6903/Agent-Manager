"""Generic repository for integration sync state with optimistic locking."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, and_, update
from sqlalchemy.orm import Session

from agent_manager.models.gmail import IntegrationSyncState

logger = logging.getLogger("agent_manager.repositories.integration_sync")


class ConcurrentModificationError(Exception):
    """Raised when optimistic lock detects a concurrent update."""


class IntegrationSyncRepository:
    """Manages persistence of per-agent, per-integration sync state.

    Uses optimistic locking (version column) to prevent concurrent tasks
    from overwriting each other's cursor state.
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

        Uses optimistic locking: if another task updated the row concurrently,
        raises ConcurrentModificationError instead of silently overwriting.
        """
        state = self.get(agent_id)
        if state:
            current_version = state.version
            result = self.db.execute(
                update(IntegrationSyncState)
                .where(
                    and_(
                        IntegrationSyncState.id == state.id,
                        IntegrationSyncState.version == current_version,
                    )
                )
                .values(
                    sync_cursor=cursor,
                    last_synced_at=datetime.now(timezone.utc),
                    total_fetched=IntegrationSyncState.total_fetched + fetched_count,
                    version=current_version + 1,
                )
            )
            self.db.commit()

            if result.rowcount == 0:
                logger.error(
                    "Optimistic lock failed for %s/%s (version=%d) — concurrent modification detected",
                    agent_id, self.integration_name, current_version,
                )
                raise ConcurrentModificationError(
                    f"Sync state for {agent_id}/{self.integration_name} was modified by another task"
                )

            self.db.refresh(state)
        else:
            state = IntegrationSyncState(
                agent_id=agent_id,
                integration_name=self.integration_name,
                sync_cursor=cursor,
                last_synced_at=datetime.now(timezone.utc),
                total_fetched=fetched_count,
                version=1,
            )
            self.db.add(state)
            self.db.commit()
            self.db.refresh(state)

        return state

    def clear(self, agent_id: str) -> None:
        """Reset sync state — forces a full re-fetch on next run."""
        state = self.get(agent_id)
        if state:
            self.db.delete(state)
            self.db.commit()
