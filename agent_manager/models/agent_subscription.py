"""Agent subscription model — tracks monthly billing for each agent."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID

from ..database import Base


class AgentSubscription(Base):
    __tablename__ = "agent_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String, unique=True, index=True, nullable=False)
    org_id = Column(String, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    status = Column(String, index=True, nullable=False, default="active")  # active / locked / deleted
    amount_cents = Column(Integer, nullable=False, default=2400)
    next_billing_date = Column(DateTime(timezone=True), nullable=False)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
