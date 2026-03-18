"""Backwards-compatible Gmail sync repository — delegates to IntegrationSyncRepository."""
from __future__ import annotations

from sqlalchemy.orm import Session

from agent_manager.repositories.integration_sync_repository import IntegrationSyncRepository


class GmailSyncRepository(IntegrationSyncRepository):
    """Gmail-specific sync state repository.

    Thin wrapper so existing callers (``GmailSyncRepository(db)``) keep working
    without changes. All logic lives in the generic parent class.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db, integration_name="gmail")

    # Alias for Gmail-specific naming used in existing callers
    def save_history_id(
        self, agent_id: str, history_id: str, fetched_count: int = 0,
    ):
        return self.save_cursor(agent_id, history_id, fetched_count)
