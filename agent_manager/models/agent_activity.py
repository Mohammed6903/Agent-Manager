"""Agent Activity model — unified activity stream for all agent actions."""

from datetime import datetime, timezone
import uuid

from sqlalchemy import Column, String, Integer, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB

from ..database import Base


class AgentActivity(Base):
    __tablename__ = "agent_activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String, nullable=False, index=True)
    activity_type = Column(String, nullable=False, index=True)
    summary = Column(String, nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=True)
    status = Column(String, nullable=False, default="success")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    __table_args__ = (
        Index("ix_agent_activity_agent_created", "agent_id", "created_at"),
    )
