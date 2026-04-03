"""Pydantic request schemas for Resend endpoints."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ResendApiRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Resend integration assigned.")
    method: str = Field(..., description="HTTP method (GET, POST, PUT, PATCH, DELETE).")
    path: str = Field(..., description="API path (e.g. /users/me).")
    params: Optional[Dict[str, Any]] = Field(None, description="Query parameters.")
    json_body: Optional[Dict[str, Any]] = Field(None, description="JSON request body.")
    data: Optional[Dict[str, Any]] = Field(None, description="Form-encoded request body.")
