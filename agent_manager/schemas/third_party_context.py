"""Pydantic schemas for third-party context endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ThirdPartyContextCreate(BaseModel):
    agent_id: str = Field(..., description="The owning agent ID")
    integration_name: str = Field(
        default="gmail",
        description="Integration to ingest (currently only 'gmail')",
    )
    force_full_sync: bool = Field(
        default=False,
        description="Discard stored sync checkpoint and re-ingest from scratch",
    )


class ThirdPartyContextResponse(BaseModel):
    id: UUID
    agent_id: str
    integration_name: str
    integration_metadata: Optional[dict[str, Any]] = None
    celery_task_id: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ThirdPartyContextListResponse(BaseModel):
    contexts: list[ThirdPartyContextResponse]


class ThirdPartyContextAssignRequest(BaseModel):
    agent_id: str = Field(..., description="The agent to assign this context to")


class ThirdPartyContextAssignResponse(BaseModel):
    id: UUID
    agent_id: str
    context_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
