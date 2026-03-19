"""Backwards-compatible Calendar sync repository — delegates to IntegrationSyncRepository."""
from __future__ import annotations

from sqlalchemy.orm import Session

from agent_manager.repositories.integration_sync_repository import IntegrationSyncRepository


class CalendarSyncRepository(IntegrationSyncRepository):
    """Calendar-specific sync state repository.

    Thin wrapper so existing callers (``CalendarSyncRepository(db)``) keep working
    without changes. All logic lives in the generic parent class.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db, integration_name="google_calendar")

    # Alias for Calendar-specific naming used in existing callers
    def save_sync_token(
        self, agent_id: str, sync_token: str, fetched_count: int = 0,
    ):
        return self.save_cursor(agent_id, sync_token, fetched_count)
