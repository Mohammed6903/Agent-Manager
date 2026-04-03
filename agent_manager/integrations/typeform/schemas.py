"""Pydantic request schemas for Typeform endpoints."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class TypeformAgentRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Typeform integration assigned.")


class TypeformListFormsRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Typeform integration assigned.")
    page: Optional[int] = Field(None, description="Page number.")
    page_size: Optional[int] = Field(None, description="Number of results per page.")


class TypeformFormIdRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Typeform integration assigned.")
    form_id: str = Field(..., description="Form ID.")


class TypeformCreateFormRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Typeform integration assigned.")
    form_data: Dict[str, Any] = Field(..., description="Form definition object with title, fields, etc.")


class TypeformUpdateFormRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Typeform integration assigned.")
    form_data: Dict[str, Any] = Field(..., description="Updated form definition.")


class TypeformListResponsesRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Typeform integration assigned.")
    form_id: str = Field(..., description="Form ID.")
    page_size: Optional[int] = Field(None, description="Number of responses per page (max 1000).")
    since: Optional[str] = Field(None, description="ISO 8601 date to filter responses after.")
    until: Optional[str] = Field(None, description="ISO 8601 date to filter responses before.")
    after: Optional[str] = Field(None, description="Pagination token.")


class TypeformWorkspaceIdRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Typeform integration assigned.")
    workspace_id: str = Field(..., description="Workspace ID.")
