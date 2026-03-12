"""Router for third-party context CRUD and assignment endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.third_party_context import (
    ThirdPartyContextAssignRequest,
    ThirdPartyContextAssignResponse,
    ThirdPartyContextCreate,
    ThirdPartyContextListResponse,
    ThirdPartyContextResponse,
)
from ..services.third_party_context_service import ThirdPartyContextService

router = APIRouter(tags=["Third-Party Contexts"])


def _get_service(db: Session = Depends(get_db)) -> ThirdPartyContextService:
    return ThirdPartyContextService(db)


# ── Context CRUD ─────────────────────────────────────────────────────────────


@router.post("", response_model=dict)
def create_context(
    req: ThirdPartyContextCreate,
    svc: ThirdPartyContextService = Depends(_get_service),
):
    """Create a new third-party context and trigger ingestion."""
    return svc.create_gmail_context(req.agent_id, req.force_full_sync)


@router.delete("/{context_id}", status_code=202)
def delete_context(
    context_id: uuid.UUID,
    svc: ThirdPartyContextService = Depends(_get_service),
):
    """Enqueue background deletion of a context and all associated data (S3, Qdrant, DB).

    Returns 202 Accepted immediately with a task_id that can be polled for progress.
    """
    return svc.purge_gmail_context_data(context_id)


@router.get("", response_model=ThirdPartyContextListResponse)
def list_contexts(
    agent_id: str,
    svc: ThirdPartyContextService = Depends(_get_service),
):
    """List all third-party contexts assigned to an agent."""
    contexts = svc.list_contexts_for_agent(agent_id)
    return ThirdPartyContextListResponse(contexts=contexts)


@router.get("/completed", response_model=ThirdPartyContextListResponse)
def list_completed_contexts(
    svc: ThirdPartyContextService = Depends(_get_service),
):
    """List all third-party contexts whose ingestion task completed successfully."""
    contexts = svc.get_all_complete_contexts()
    return ThirdPartyContextListResponse(contexts=contexts)


@router.get("/{context_id}", response_model=ThirdPartyContextResponse)
def get_context(
    context_id: uuid.UUID,
    svc: ThirdPartyContextService = Depends(_get_service),
):
    """Get a single third-party context with its status."""
    return svc.get_context(context_id)


# ── Assignment ───────────────────────────────────────────────────────────────


@router.post(
    "/{context_id}/assign",
    response_model=ThirdPartyContextAssignResponse,
)
def assign_context(
    context_id: uuid.UUID,
    req: ThirdPartyContextAssignRequest,
    svc: ThirdPartyContextService = Depends(_get_service),
):
    """Assign a third-party context to an agent."""
    return svc.assign_context(context_id, req.agent_id)


@router.delete("/{context_id}/assign/{agent_id}")
def unassign_context(
    context_id: uuid.UUID,
    agent_id: str,
    svc: ThirdPartyContextService = Depends(_get_service),
):
    """Remove a third-party context assignment from an agent."""
    svc.unassign_context(context_id, agent_id)
    return Response(status_code=204)
