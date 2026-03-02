from datetime import datetime
from typing import List, Optional, Any, Dict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# --- Global Integration ---

class EndpointSchema(BaseModel):
    method: str
    path: str
    description: str

class AuthFieldSchema(BaseModel):
    name: str
    label: str
    required: bool

class GlobalIntegrationCreate(BaseModel):
    name: str
    type: str
    api_type: str = Field(default="rest", description="API type: 'rest' or 'graphql'")
    status: str = "active"
    base_url: str
    auth_scheme: Dict[str, Any] = Field(default_factory=dict)
    auth_fields: List[AuthFieldSchema]
    endpoints: List[EndpointSchema]
    request_transformers: List[Dict[str, Any]] = Field(default_factory=list, description="Field mapping rules for requests")
    response_transformers: List[Dict[str, Any]] = Field(default_factory=list, description="Field mapping rules for responses")
    usage_instructions: str

class GlobalIntegrationUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    api_type: Optional[str] = None
    status: Optional[str] = None
    base_url: Optional[str] = None
    auth_scheme: Optional[Dict[str, Any]] = None
    auth_fields: Optional[List[AuthFieldSchema]] = None
    endpoints: Optional[List[EndpointSchema]] = None
    request_transformers: Optional[List[Dict[str, Any]]] = None
    response_transformers: Optional[List[Dict[str, Any]]] = None
    usage_instructions: Optional[str] = None

class GlobalIntegrationResponse(BaseModel):
    id: UUID
    name: str
    type: str
    api_type: str
    status: str
    base_url: str
    auth_scheme: Dict[str, Any]
    auth_fields: List[AuthFieldSchema]
    endpoints: List[EndpointSchema]
    request_transformers: List[Dict[str, Any]]
    response_transformers: List[Dict[str, Any]]
    usage_instructions: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# --- Agent Integration ---

class AgentIntegrationAssignRequest(BaseModel):
    agent_id: str
    credentials: Dict[str, str] = Field(..., description="Values answering the auth_fields schema")

class AgentIntegrationResponse(BaseModel):
    id: UUID
    agent_id: str
    integration_id: UUID
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class AgentAssignedIntegrationDetail(BaseModel):
    """Returned to the agent to know how to use it"""
    integration_id: UUID
    name: str
    type: str
    api_type: str
    base_url: str
    auth_scheme: Dict[str, Any]
    auth_fields: List[AuthFieldSchema]
    usage_instructions: str


class AgentIntegrationListResponse(BaseModel):
    integrations: List[AgentAssignedIntegrationDetail]


class IntegrationProxyRequest(BaseModel):
    agent_id: str
    method: str
    path: str
    body: dict = Field(default_factory=dict)
    headers: dict = Field(default_factory=dict)
    params: dict = Field(default_factory=dict)


class IntegrationProxyGraphQLRequest(BaseModel):
    """Proxy request for GraphQL integrations."""
    agent_id: str
    query: str = Field(..., description="GraphQL query or mutation string")
    variables: Optional[Dict[str, Any]] = Field(default=None, description="GraphQL variables")
    operation_name: Optional[str] = Field(default=None, description="GraphQL operation name")
    headers: Dict[str, str] = Field(default_factory=dict)

# --- Integration Logs ---

class IntegrationLogCreate(BaseModel):
    integration_id: UUID
    agent_id: str
    method: str
    endpoint: str
    status_code: int
    duration_ms: int

class IntegrationLogResponse(BaseModel):
    id: UUID
    integration_id: UUID
    agent_id: str
    method: str
    endpoint: str
    status_code: int
    duration_ms: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class IntegrationLogListResponse(BaseModel):
    logs: List[IntegrationLogResponse]
