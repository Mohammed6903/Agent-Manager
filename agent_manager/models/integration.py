from datetime import datetime, timezone
import uuid

from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from ..database import Base


class AgentIntegration(Base):
    __tablename__ = "agent_integrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String, index=True, nullable=False)
    integration_name = Column(String, index=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class IntegrationLog(Base):
    __tablename__ = "integration_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    integration_name = Column(String, index=True, nullable=False)
    agent_id = Column(String, index=True, nullable=False)
    
    method = Column(String, nullable=False)
    endpoint = Column(String, nullable=False)
    status_code = Column(Integer, nullable=False)
    duration_ms = Column(Integer, nullable=False, default=0)
    
    request_id = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
