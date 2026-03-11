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


class GmailSyncState(Base):
    __tablename__ = "gmail_sync_state"

    agent_id = Column(String, primary_key=True, index=True)
    # None = never synced
    history_id = Column(String, nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    total_fetched = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())