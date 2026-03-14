import asyncio
import json
import uuid
from typing import List

from celery.contrib.abortable import AbortableAsyncResult
from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..celery_app import celery_app
from ..database import get_db
from ..schemas.context import (
    AgentContextAssignRequest,
    AgentContextResponse,
    ContextContentResponse,
    ContextListResponse,
    GlobalContextCreate,
    GlobalContextResponse,
    GlobalContextUpdate,
)
from ..services.context_service import ContextService
from ..services.third_party_context_service import ThirdPartyContextService
from ..tasks.gmail_ingest_task import get_active_tasks

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


# -- Agent Contexts --

@router.get("/agent/{agent_id}", response_model=ContextListResponse)
def get_agent_contexts(
    agent_id: str,
    svc: ContextService = Depends(get_context_service),
):
    """List contexts assigned to the agent."""
    contexts = svc.get_available_contexts_for_agent(agent_id)
    return ContextListResponse(contexts=contexts)

@router.get("/{context_id}/content", response_model=ContextContentResponse)
def get_context_content(
    context_id: uuid.UUID,
    agent_id: str,
    svc: ContextService = Depends(get_context_service),
):
    """Fetch the content of an assigned context."""
    content = svc.get_context_content_for_agent(agent_id, context_id)
    context = svc.get_global_context_by_id(context_id)
    return ContextContentResponse(id=context.id, name=context.name, content=content)

@router.get("/ram/context/active")
def list_active_tasks():
    """Return all in-flight context sync tasks with their live Celery state."""
    active = get_active_tasks()
    rows = []
    for key, task_id in active.items():
        parts = key.split(":")
        if len(parts) == 3:
            # New format: integration:type:agent_id
            integration_name, task_type, agent_id = parts
        elif len(parts) == 2:
            # Old format: integration:agent_id
            integration_name, agent_id = parts
            task_type = "ingest"
        else:
            # Fallback
            integration_name = "gmail"
            agent_id = key
            task_type = "ingest"

        rows.append(
            {
                "agent_id": agent_id,
                "integration": integration_name,
                "task_type": task_type,
                "task_id": task_id,
                "status": celery_app.AsyncResult(task_id).state,
            }
        )
    return rows


@router.post("/ram/context/gmail")
def create_gmail_context(
    agent_id: str,
    force_full_sync: bool = False,
    db: Session = Depends(get_db),
):
    """Start a unified Gmail ingest + pipeline job for an agent.

    Validates that Gmail is assigned and credentials are valid, creates a
    ThirdPartyContext tracking row, and enqueues the background task.

    Set ``force_full_sync=true`` to discard any stored sync checkpoint and
    re-ingest the entire mailbox from scratch.
    """
    return ThirdPartyContextService(db).create_gmail_context(agent_id, force_full_sync)


@router.delete("/ram/context/{context_id}/data")
def purge_context_data(
    context_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Delete context data from S3, Qdrant, and remove the context DB row."""
    return ThirdPartyContextService(db).purge_gmail_context_data(context_id)


@router.get("/ram/task/{task_id}/progress")
async def task_progress(task_id: str):
    """SSE stream — connect here to watch progress for any background task."""

    async def event_stream():
        while True:
            result = celery_app.AsyncResult(task_id)
            try:
                state = result.state
                info = result.info or {}
            except Exception:
                # Celery couldn't deserialize the stored failure result (e.g. missing
                # exc_type on a retry exception). Emit a clean FAILURE event and stop.
                yield f'data: {json.dumps({"task_id": task_id, "status": "FAILED", "message": "Task failed — check worker logs for details."})}\n\n'
                break

            data = {
                "task_id": task_id,
                "status": state,
                **(info if isinstance(info, dict) else {"message": str(info)}),
            }
            yield f"data: {json.dumps(data)}\n\n"

            if state in ("SUCCESS", "FAILURE", "FAILED", "REVOKED"):
                break

            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/ram/task/{task_id}")
def cancel_task(task_id: str):
    """Cancel any running Celery task by ID.

    Sends a cooperative abort signal (for AbortableTask-based tasks) and also
    revokes the task so it won't start if it is still queued.
    """
    AbortableAsyncResult(task_id, app=celery_app).abort()
    celery_app.control.revoke(task_id)
    state = celery_app.AsyncResult(task_id).state
    return {
        "task_id": task_id,
        "status": "cancellation requested",
        "current_state": state,
    }
