from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

class GlobalContextCreate(BaseModel):
    name: str = Field(..., description="Unique name for the context")
    content: str = Field(..., description="The knowledge content")

class GlobalContextResponse(BaseModel):
    id: UUID
    name: str
    content: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class GlobalContextUpdate(BaseModel):
    name: Optional[str] = Field(None, description="New name for the context")
    content: Optional[str] = Field(None, description="New content for the context")

class AgentContextAssignRequest(BaseModel):
    agent_id: str = Field(..., description="The ID of the agent")
    context_id: str = Field(..., description="The ID of the context to assign")

class AgentContextResponse(BaseModel):
    id: UUID
    agent_id: str
    context_id: UUID
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class ContextNameListResponse(BaseModel):
    contexts: List[str]

class ContextListResponse(BaseModel):
    contexts: List[GlobalContextResponse]

class ContextContentResponse(BaseModel):
    id: UUID
    name: str
    content: str
