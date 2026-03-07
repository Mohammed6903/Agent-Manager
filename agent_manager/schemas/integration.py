from datetime import datetime
from typing import List, Optional, Any, Dict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EndpointSchema(BaseModel):
    method: str
    path: str
    description: str

class AuthFieldSchema(BaseModel):
    name: str
    label: str
    required: bool


# --- Available Integrations Response ---

class ConnectedAgentInfo(BaseModel):
    agent_id: str
    name: str
    integration_metadata: Optional[Dict[str, Any]] = None

class IntegrationDefResponse(BaseModel):
    name: str
    display_name: str
    api_type: str
    base_url: str
    auth_scheme: Dict[str, Any]
    auth_fields: List[AuthFieldSchema]
    endpoints: List[EndpointSchema]
    usage_instructions: str
    connected_agents: List[ConnectedAgentInfo] = []


# --- Agent Integration ---

class AgentIntegrationAssignRequest(BaseModel):
    agent_id: str
    integration_name: str
    credentials: Optional[Dict[str, str]] = Field(
        default=None,
        description="Required for static auth integrations. Not needed for OAuth integrations — the assign endpoint will redirect to the provider's authorization page instead."
    )

class AgentIntegrationResponse(BaseModel):
    id: UUID
    agent_id: str
    integration_name: str
    created_at: datetime
    integration_metadata: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(from_attributes=True)

class AgentAssignedIntegrationDetail(BaseModel):
    """Returned to the agent to know how to use it"""
    id: str
    integration_name: str
    name: str
    display_name: str
    api_type: str
    base_url: str
    auth_scheme: Dict[str, Any]
    auth_fields: List[AuthFieldSchema]
    usage_instructions: str
    integration_metadata: Optional[Dict[str, Any]] = None


class AgentIntegrationListResponse(BaseModel):
    integrations: List[AgentAssignedIntegrationDetail]


# --- Integration Logs ---

class IntegrationLogResponse(BaseModel):
    id: UUID
    integration_name: str
    agent_id: str
    method: str
    endpoint: str
    status_code: int
    duration_ms: int
    request_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class IntegrationLogListResponse(BaseModel):
    logs: List[IntegrationLogResponse]
