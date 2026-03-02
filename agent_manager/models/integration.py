from datetime import datetime, timezone
import uuid

from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB

from ..database import Base


class GlobalIntegration(Base):
    __tablename__ = "global_integrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, index=True, nullable=False)
    type = Column(String, nullable=False)  # e.g., "slack", "notion"
    api_type = Column(String, nullable=False, default="rest")  # "rest" or "graphql"
    status = Column(
        SAEnum("active", "inactive", "error", name="integration_status"),
        nullable=False,
        default="active",
    )
    base_url = Column(String, nullable=False)
    auth_scheme = Column(JSONB, nullable=False, server_default='{}')
    auth_fields = Column(JSONB, nullable=False, default=list) # e.g. [{"name": "bot_token", "label": "Bot Token", "required": true}]
    endpoints = Column(JSONB, nullable=False, default=list) # e.g. [{"method": "POST", "path": "/chat.postMessage", "description": "Send a message"}]
    request_transformers = Column(JSONB, nullable=False, default=list)  # field mapping rules for normalizing outgoing requests
    response_transformers = Column(JSONB, nullable=False, default=list)  # field mapping rules for normalizing responses
    usage_instructions = Column(Text, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AgentIntegration(Base):
    __tablename__ = "agent_integrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String, index=True, nullable=False)
    integration_id = Column(UUID(as_uuid=True), ForeignKey("global_integrations.id", ondelete="CASCADE"), nullable=False, index=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class IntegrationLog(Base):
    __tablename__ = "integration_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    integration_id = Column(UUID(as_uuid=True), ForeignKey("global_integrations.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(String, index=True, nullable=False)
    
    method = Column(String, nullable=False)
    endpoint = Column(String, nullable=False)
    status_code = Column(Integer, nullable=False)
    duration_ms = Column(Integer, nullable=False, default=0)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
