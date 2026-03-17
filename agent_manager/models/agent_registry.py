"""Agent registry — fast local cache of agent metadata with org scoping."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID
from ..database import Base


class AgentRegistry(Base):
    __tablename__ = "agent_registry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    org_id = Column(String, index=True, nullable=True)   # None = unscoped / legacy
    user_id = Column(String, index=True, nullable=True)  # who created it
    workspace = Column(String, nullable=True)
    agent_dir = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        # Most common query: all agents for a given org
        Index("ix_agent_registry_org_id_agent_id", "org_id", "agent_id"),
    )