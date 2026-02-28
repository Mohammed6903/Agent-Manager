from typing import List
import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.context import (
    GlobalContextCreate,
    GlobalContextUpdate,
    GlobalContextResponse,
    AgentContextAssignRequest,
    AgentContextResponse,
    ContextNameListResponse,
    ContextListResponse,
    ContextContentResponse,
)
from ..services.context_service import ContextService

router = APIRouter(tags=["Context Management"])

def get_context_service(db: Session = Depends(get_db)) -> ContextService:
    return ContextService(db)

# -- Global CRUD --

@router.post("", response_model=GlobalContextResponse)
def create_global_context(
    req: GlobalContextCreate,
    svc: ContextService = Depends(get_context_service),
):
    """Create a new global context."""
    return svc.create_global_context(req)

@router.get("", response_model=List[GlobalContextResponse])
def list_global_contexts(
    svc: ContextService = Depends(get_context_service),
):
    """List all available global contexts."""
    return svc.list_global_contexts()

@router.get("/{context_id}", response_model=GlobalContextResponse)
def get_global_context(
    context_id: uuid.UUID,
    svc: ContextService = Depends(get_context_service),
):
    """Get a specific global context."""
    return svc.get_global_context_by_id(context_id)

@router.patch("/{context_id}", response_model=GlobalContextResponse)
def update_global_context(
    context_id: uuid.UUID,
    req: GlobalContextUpdate,
    svc: ContextService = Depends(get_context_service),
):
    """Update a specific global context."""
    return svc.update_global_context(context_id, req)
    
@router.delete("/{context_id}")
def delete_global_context(
    context_id: uuid.UUID,
    svc: ContextService = Depends(get_context_service),
):
    """Delete a specific global context."""
    svc.delete_global_context(context_id)
    return Response(status_code=204)


# -- Agent Assignment --

@router.post("/assign", response_model=AgentContextResponse)
def assign_context_to_agent(
    req: AgentContextAssignRequest,
    svc: ContextService = Depends(get_context_service),
):
    """Assign a global context to an agent."""
    return svc.assign_context(req)

@router.delete("/unassign/{agent_id}/{context_id}")
def unassign_context_from_agent(
    agent_id: str,
    context_id: uuid.UUID,
    svc: ContextService = Depends(get_context_service),
):
    """Unassign a global context from an agent."""
    svc.unassign_context(agent_id, context_id)
    return Response(status_code=204)


# -- Agent Skills --

@router.get("/agent/{agent_id}", response_model=ContextListResponse)
def get_agent_contexts(
    agent_id: str,
    svc: ContextService = Depends(get_context_service),
):
    """(Skill Endpoint) List contexts assigned to the agent."""
    contexts = svc.get_available_contexts_for_agent(agent_id)
    return ContextListResponse(contexts=contexts)

@router.get("/{context_id}/content", response_model=ContextContentResponse)
def get_context_content(
    context_id: uuid.UUID,
    agent_id: str,
    svc: ContextService = Depends(get_context_service),
):
    """(Skill Endpoint) Fetch the content of an assigned context."""
    content = svc.get_context_content_for_agent(agent_id, context_id)
    context = svc.get_global_context_by_id(context_id)
    return ContextContentResponse(id=context.id, name=context.name, content=content)
