"""Dead Letter Queue for failed ingestion items."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID

from ..database import Base


class FailedIngestion(Base):
    __tablename__ = "failed_ingestions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String, nullable=False, index=True)
    integration_name = Column(String, nullable=False, index=True)
    message_id = Column(String, nullable=False)  # external ID (e.g., Gmail message ID)
    phase = Column(String, nullable=False)  # "ingest" or "pipeline"
    error = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    status = Column(String, default="pending", nullable=False, index=True)  # pending, retrying, resolved, permanently_failed
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_retried_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_failed_ingestions_agent_integration", "agent_id", "integration_name"),
        Index("ix_failed_ingestions_status_retry", "status", "retry_count"),
    )
