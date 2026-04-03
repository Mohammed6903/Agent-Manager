from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class PostHogApiRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the PostHog integration assigned.")
    method: str = Field(..., description="HTTP method.")
    path: str = Field(..., description="API path.")
    params: Optional[Dict[str, Any]] = Field(None, description="Query parameters.")
    json_body: Optional[Dict[str, Any]] = Field(None, description="JSON request body.")
    data: Optional[Dict[str, Any]] = Field(None, description="Form-encoded request body.")
