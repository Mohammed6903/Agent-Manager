"""SQLAlchemy model for tracking third-party integration sync jobs."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from ..database import Base


class ThirdPartyContext(Base):
    """Tracks a background ingest + pipeline job for a third-party integration.

    Status lifecycle: pending → ingesting → processing → complete | failed | cancelled
    """

    __tablename__ = "third_party_contexts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String, index=True, nullable=False)
    integration_name = Column(String, nullable=False)
    # Snapshot of the integration_metadata at the time the job was created
    integration_metadata = Column(JSONB, nullable=True)

    # Celery task ID — set after the task has been enqueued
    celery_task_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending")

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
