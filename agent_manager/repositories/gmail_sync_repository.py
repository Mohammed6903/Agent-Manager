"""Repository for Gmail sync state."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.gmail import GmailSyncState


class GmailSyncRepository:
    """Manages persistence of per-agent Gmail sync state."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, agent_id: str) -> GmailSyncState | None:
        """Return the sync state for *agent_id*, or None if not found."""
        return self.db.execute(
            select(GmailSyncState).where(GmailSyncState.agent_id == agent_id)
        ).scalar_one_or_none()

    def save_history_id(
        self, agent_id: str, history_id: str, fetched_count: int = 0
    ) -> GmailSyncState:
        """Create or update sync state after a successful sync."""
        state = self.get(agent_id)
        if state:
            state.history_id = history_id
            state.last_synced_at = datetime.now(timezone.utc)
            state.total_fetched += fetched_count
        else:
            state = GmailSyncState(
                agent_id=agent_id,
                history_id=history_id,
                last_synced_at=datetime.now(timezone.utc),
                total_fetched=fetched_count,
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