"""Router for third-party context CRUD and assignment endpoints."""
from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Response, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_agent_service
from ..schemas.third_party_context import (
    AvailableAgentsResponse,
    ThirdPartyContextAssignRequest,
    ThirdPartyContextCreate,
    ThirdPartyContextListResponse,
    ThirdPartyContextResponse,
)
from ..services.agent_service import AgentService
from ..services.third_party_context_service import ThirdPartyContextService

router = APIRouter(tags=["Third-Party Contexts"])


def _get_service(
    db: Session = Depends(get_db),
    agent_service: AgentService = Depends(get_agent_service),
) -> ThirdPartyContextService:
    return ThirdPartyContextService(db, agent_service)


# ── Context CRUD ─────────────────────────────────────────────────────────────


@router.post("", response_model=dict)
async def create_context(
    req: ThirdPartyContextCreate,
    svc: ThirdPartyContextService = Depends(_get_service),
):
    """Create a new third-party context and trigger ingestion."""
    return await svc.create_context(req.integration_name, req.agent_id, req.force_full_sync)


@router.delete("/{context_id}", status_code=202)
async def delete_context(
    context_id: uuid.UUID,
    svc: ThirdPartyContextService = Depends(_get_service),
):
    """Enqueue background deletion of a context and all associated data."""
    return await svc.purge_context_data(context_id)


@router.get("", response_model=ThirdPartyContextListResponse)
async def list_contexts(
    agent_id: str,
    svc: ThirdPartyContextService = Depends(_get_service),
    org_id: Optional[str] = Query(default=None),
):
    contexts = await svc.list_contexts_for_agent(agent_id, org_id=org_id)
    return ThirdPartyContextListResponse(contexts=contexts)


@router.get("/completed", response_model=ThirdPartyContextListResponse)
async def list_completed_contexts(
    svc: ThirdPartyContextService = Depends(_get_service),
    org_id: Optional[str] = Query(default=None),
):
    contexts = await svc.get_all_complete_contexts(org_id=org_id)
    return ThirdPartyContextListResponse(contexts=contexts)


@router.get("/{context_id}", response_model=ThirdPartyContextResponse)
async def get_context(
    context_id: uuid.UUID,
    svc: ThirdPartyContextService = Depends(_get_service),
    org_id: Optional[str] = Query(default=None),
):
    return await svc.get_context(context_id, org_id=org_id)


# ── Assignment ───────────────────────────────────────────────────────────────


@router.get(
    "/{context_id}/available-agents",
    response_model=AvailableAgentsResponse,
)
async def get_available_agents(
    context_id: uuid.UUID,
    svc: ThirdPartyContextService = Depends(_get_service),
    org_id: Optional[str] = Query(default=None, description="Filter candidates to agents in this org"),
):
    agents = await svc.get_available_agents(context_id, org_id=org_id)
    return AvailableAgentsResponse(agents=agents)


@router.post("/{context_id}/assign", response_model=ThirdPartyContextResponse)
async def assign_context(
    context_id: uuid.UUID,
    req: ThirdPartyContextAssignRequest,
    svc: ThirdPartyContextService = Depends(_get_service),
):
    return await svc.assign_context(context_id, req.agent_id)


@router.delete("/{context_id}/assign/{agent_id}")
def unassign_context(
    context_id: uuid.UUID,
    agent_id: str,
    svc: ThirdPartyContextService = Depends(_get_service),
):
    """Remove a third-party context assignment from an agent."""
    svc.unassign_context(context_id, agent_id)
    return Response(status_code=204)
