"""Gmail-related SQLAlchemy models."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB

from ..database import Base


class GoogleAccount(Base):
    __tablename__ = "google_accounts"

    agent_id = Column(String, primary_key=True, index=True)
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=True)
    expiry = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class AgentSecret(Base):
    __tablename__ = "agent_secrets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(50), nullable=False)
    service_name = Column(String(50), nullable=False)
    secret_data = Column(JSONB, nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("agent_id", "service_name", name="uq_agent_service"),
    )


class IntegrationSyncState(Base):
    """Unified sync state for all third-party integrations.

    ``sync_cursor`` is opaque — Gmail stores a historyId, Calendar stores
    a nextSyncToken, future integrations store whatever their API needs.
    """
    __tablename__ = "integration_sync_state"

    agent_id = Column(String, nullable=False, index=True)
    integration_name = Column(String, nullable=False)
    # Opaque cursor: historyId (Gmail), nextSyncToken (Calendar), etc.
    sync_cursor = Column(String, nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    total_fetched = Column(Integer, default=0)
    version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("agent_id", "integration_name", name="uq_agent_integration_sync"),
        {"extend_existing": True},
    )
    # Composite PK workaround: use agent_id as PK and integration_name as part of unique
    id = Column(Integer, primary_key=True, autoincrement=True)


# Backwards-compat aliases — kept so existing imports don't break during migration
GmailSyncState = IntegrationSyncState
CalendarSyncState = IntegrationSyncState