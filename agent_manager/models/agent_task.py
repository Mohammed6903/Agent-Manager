"""AgentTask model — AI-agent-driven task/kanban board."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, DateTime, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB

from ..database import Base


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    status = Column(
        SAEnum("assigned", "in_progress", "completed", "error", name="task_status"),
        nullable=False,
        default="assigned",
    )
    difficulty = Column(
        SAEnum("low", "medium", "high", name="task_difficulty"),
        nullable=False,
        default="medium",
    )

    # Nested structures stored as JSONB
    sub_tasks = Column(JSONB, nullable=False, default=list)        # [{text, done}]
    context_pages = Column(JSONB, nullable=False, default=list)    # [{context_name, context_id}]
    integrations = Column(JSONB, nullable=False, default=list)     # [str]
    issues = Column(JSONB, nullable=False, default=list)           # [{description, resolved}]

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
