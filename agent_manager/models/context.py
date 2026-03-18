from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from ..database import Base

class GlobalContext(Base):
    __tablename__ = "global_contexts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=False)
    org_id = Column(String, nullable=True, index=True)  # None = legacy/global
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        # Name must be unique within an org (or within unscoped if org_id is None)
        UniqueConstraint("name", "org_id", name="uq_global_context_name_org"),
        Index("ix_global_contexts_org_id", "org_id"),
    )


class AgentContext(Base):
    __tablename__ = "agent_contexts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String, index=True, nullable=False)
    context_id = Column(
        UUID(as_uuid=True),
        ForeignKey("global_contexts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))