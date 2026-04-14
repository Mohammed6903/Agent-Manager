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
    # The user whose action produced this activity, when known. NULL for
    # system-generated activity (heartbeats, cron runs triggered by the
    # scheduler, async context jobs where no human user initiated the
    # work). Activity feeds for employees filter on this; founders see
    # everything including NULL rows.
    user_id = Column(String, nullable=True, index=True)
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
        # Per-user activity feed for employees — agent_id + user_id +
        # time ordering is the hot path. Null user_id rows are skipped
        # for employees (covered by the agent_id-only index).
        Index("ix_agent_activity_agent_user_created", "agent_id", "user_id", "created_at"),
    )
