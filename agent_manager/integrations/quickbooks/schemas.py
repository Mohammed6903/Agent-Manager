"""Pydantic request schemas for QuickBooks endpoints."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class QuickBooksApiRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the QuickBooks integration assigned.")
    method: str = Field(..., description="HTTP method (GET, POST, PUT, PATCH, DELETE).")
    path: str = Field(..., description="API path.")
    params: Optional[Dict[str, Any]] = Field(None, description="Query parameters.")
    json_body: Optional[Dict[str, Any]] = Field(None, description="JSON request body.")
    data: Optional[Dict[str, Any]] = Field(None, description="Form-encoded request body.")
