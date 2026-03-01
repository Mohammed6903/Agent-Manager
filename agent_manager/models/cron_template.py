"""Cron Template SQLAlchemy models."""

from sqlalchemy import Column, String, DateTime, Boolean, JSON, Text, func
import uuid

from ..database import Base


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
    required_integrations = Column(JSON, default=list) # e.g. ["gmail", "notion"]
    variables = Column(JSON, default=list)             # e.g. [{"key": "notion_page_id", "label": "Notion Page ID", "required": true, "default": null}]
    
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
