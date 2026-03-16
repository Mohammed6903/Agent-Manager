"""Chat Usage tracking model for OpenClaw session logs."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, DateTime, Float
from sqlalchemy.dialects.postgresql import UUID

from ..database import Base

class ChatUsageLog(Base):
    __tablename__ = "chat_usage_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Storing the unique turn/message ID from OpenClaw to prevent double-counting
    message_id = Column(String, unique=True, index=True, nullable=False) 
    
    user_id = Column(String, index=True, nullable=False)
    session_id = Column(String, index=True, nullable=False)
    agent_id = Column(String, index=True, nullable=True) # Nullable for direct/global models
    model = Column(String, index=True, nullable=False)
    
    prompt_tokens = Column(Integer, default=0, nullable=False)
    completion_tokens = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, default=0, nullable=False)

    input_cost = Column(Float, default=0.0, nullable=False)
    output_cost = Column(Float, default=0.0, nullable=False)
    total_cost = Column(Float, default=0.0, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))