"""Cron Template SQLAlchemy models."""

from sqlalchemy import Column, String, DateTime, Boolean, JSON, Text, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from ..database import Base


class CronTemplateIntegration(Base):
    __tablename__ = "cron_template_integrations"
    template_id = Column(String, ForeignKey("cron_templates.id", ondelete="CASCADE"), primary_key=True)
    integration_id = Column(UUID(as_uuid=True), ForeignKey("global_integrations.id", ondelete="CASCADE"), primary_key=True)


class CronTemplate(Base):
    __tablename__ = "cron_templates"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_by_user_id = Column(String, nullable=False, index=True)
    is_public = Column(Boolean, default=False, nullable=False, index=True)
    
    # Display fields
    name = Column(String, nullable=False)
    description = Column(String)
    category = Column(String)
    
    # Requirements
    variables = Column(JSON, default=list)             # e.g. [{"key": "notion_page_id", "label": "Notion Page ID", "required": true, "default": null}]
    
    # Relationships
    integrations = relationship("CronTemplateIntegration", cascade="all, delete-orphan")

    @property
    def required_integrations(self):
        return [i.integration_id for i in self.integrations]

    # Cron Schedule & Config Blueprint
    schedule_kind = Column(String, nullable=False)      # "at", "every", "cron"
    schedule_expr = Column(String, nullable=False)
    schedule_tz = Column(String)
    schedule_human = Column(String)
    
    session_target = Column(String, nullable=False, default="isolated")
    delivery_mode = Column(String, nullable=False, default="webhook")
    
    # Job execution blueprint
    payload_message = Column(Text, nullable=False)      # prompt containing {variable_key}
    pipeline_template = Column(JSON)                    # JSON array containing {variable_key}
    
    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

