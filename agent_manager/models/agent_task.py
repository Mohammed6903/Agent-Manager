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
    user_id = Column(String, nullable=False, index=True)
    session_id = Column(String, nullable=False, index=True)
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
    sub_tasks = Column(JSONB, nullable=False, default=list)
    context_pages = Column(JSONB, nullable=False, default=list)
    integrations = Column(JSONB, nullable=False, default=list)
    issues = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )