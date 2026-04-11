"""AgentManager router — agents, chat, sessions, cron."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Annotated, Optional

from fastapi import APIRouter, Request, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..schemas.chat import (
    ChatRequest,
    CreateAgentRequest,
    HealthResponse,
    UpdateAgentRequest,
)
from ..schemas.cron import CreateCronRequest, UpdateCronRequest, CronResponse
from ..schemas.task import CreateTaskRequest, UpdateTaskRequest, TaskResponse
from ..chat_helpers import parse_chat_request
from ..dependencies import (
    get_agent_service, get_session_service, get_chat_service, get_gateway,
    get_cron_service, get_task_service, get_usage_service
)
from ..database import get_db
from ..services.agent_service import AgentService
from ..services.session_service import SessionService
from ..services.chat_service import ChatService
from ..services.cron_service import CronService
from ..services.task_service import TaskService
from ..services.usage_service import UsageService
from ..clients.gateway_client import GatewayClient

logger = logging.getLogger("agent_manager")

router = APIRouter()

# ── Health ──────────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health(
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
    gateway: Annotated[GatewayClient, Depends(get_gateway)],
):
    """Return gateway status, agent count, and server version."""
    gateway_ok = False
    gateway_status: Any = None
    try:
        gateway_status = await gateway.get_status()
        gateway_ok = True
    except Exception as exc:
        gateway_status = {
            "error": "Could not reach OpenClaw gateway or CLI not available",
            "detail": str(exc),
        }

    agents: list = []
    agents_error: str | None = None
    try:
        agents = await agent_service.list_agents()
    except Exception as exc:
        agents_error = str(exc)

    if gateway_ok:
        overall = "ok"
    else:
        overall = "degraded"

    resp = HealthResponse(
        status=overall,
        gateway=gateway_status,
        agents_count=len(agents),
        version="1.0.0",
    )
    if agents_error:
        resp.gateway = {
            **(resp.gateway if isinstance(resp.gateway, dict) else {}),
            "agents_error": agents_error,
        }
    return resp


@router.get("/heartbeat", tags=["Health"])
async def heartbeat():
    """Simple connectivity check for integrations and health monitoring."""
    return {"status": "ok"}


# ── Agent CRUD ──────────────────────────────────────────────────────────────────

@router.post("/agents", tags=["Agents"], status_code=201)
async def create_agent(
    req: CreateAgentRequest,
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """Create a new OpenClaw agent (filesystem + gateway registration).

    Pass `org_id` in the request body to scope the agent to a specific
    organisation (Garage). Pass `user_id` for personal agent ownership
    (Network Chain).
    """
    return await agent_service.create_agent(req)


@router.get("/agents", tags=["Agents"])
async def list_agents(
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
    org_id: Optional[str] = Query(default=None, description="Filter agents by organisation ID"),
    user_id: Optional[str] = Query(default=None, description="Filter agents by user ID"),
):
    """List registered agents. Pass ?org_id= or ?user_id= to scope results."""
    return await agent_service.list_agents(org_id=org_id, user_id=user_id)


@router.get("/agents/{agent_id}", tags=["Agents"])
async def get_agent(
    agent_id: str,
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
    org_id: Optional[str] = Query(default=None, description="Verify agent belongs to this org"),
    user_id: Optional[str] = Query(default=None, description="Verify agent belongs to this user"),
):
    """Get details for a single agent. Pass ?org_id= or ?user_id= to enforce ownership check."""
    return await agent_service.get_agent(agent_id, org_id=org_id, user_id=user_id)


@router.patch("/agents/{agent_id}", tags=["Agents"])
async def update_agent(
    agent_id: str,
    req: UpdateAgentRequest,
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
    org_id: Optional[str] = Query(default=None, description="Verify agent belongs to this org before updating"),
    user_id: Optional[str] = Query(default=None, description="Verify agent belongs to this user before updating"),
):
    """Update an agent's identity, role, or personality files."""
    return await agent_service.update_agent(agent_id, req, org_id=org_id, user_id=user_id)


@router.delete("/agents/{agent_id}", tags=["Agents"])
async def delete_agent(
    agent_id: str,
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
    org_id: Optional[str] = Query(default=None, description="Verify agent belongs to this org before deleting"),
    user_id: Optional[str] = Query(default=None, description="Verify agent belongs to this user before deleting"),
):
    """Soft-delete an agent (hidden from list/get, restorable).

    Pass ?org_id= or ?user_id= to enforce ownership before deletion.
    The agent's registry row is marked deleted but preserved, the
    openclaw gateway config is updated to stop serving the agent, and
    any scheduled cron jobs it owned are cancelled. Recover via
    ``POST /api/agents/{agent_id}/restore``.
    """
    return await agent_service.delete_agent(agent_id, org_id=org_id, user_id=user_id)


@router.post("/agents/{agent_id}/restore", tags=["Agents"])
async def restore_agent(
    agent_id: str,
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
    org_id: Optional[str] = Query(default=None, description="Verify agent belongs to this org before restoring"),
    user_id: Optional[str] = Query(default=None, description="Verify agent belongs to this user before restoring"),
):
    """Restore a previously soft-deleted agent.

    Clears the ``deleted_at`` marker on the registry row, re-registers
    the agent with the openclaw gateway, and (if the subscription model
    is enforced) reactivates the subscription row. Returns 404 if no
    soft-deleted agent with this id exists for the given ownership scope.
    """
    return await agent_service.restore_agent(agent_id, org_id=org_id, user_id=user_id)



# ── Admin — shared workspace files ─────────────────────────────────────────────

from pydantic import BaseModel as _BaseModel

class _UpdateSharedFileRequest(_BaseModel):
    filename: str
    content: str


@router.post("/admin/agents/update-shared-file", tags=["Admin"])
async def update_shared_file(
    req: _UpdateSharedFileRequest,
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """Write new content to a shared workspace file (AGENTS.md or SOUL.md).

    Returns the number of agent workspaces that will see the update on their
    next session (those whose workspace symlink points to the shared file).
    """
    return await agent_service.update_shared_file(req.filename, req.content)


@router.post("/admin/agents/sync-templates", tags=["Admin"])
async def sync_templates(
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """Overwrite shared AGENTS.md / SOUL.md with the latest source templates.

    All symlinked agent workspaces will see the update on their next session.
    Use this after deploying code with updated template files.
    """
    return await agent_service.sync_templates_to_shared()


@router.post("/admin/agents/migrate-symlinks", tags=["Admin"])
async def migrate_symlinks(
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """Convert regular SOUL.md / AGENTS.md files in every agent workspace into
    symlinks pointing to the shared copies.  Idempotent — safe to run multiple
    times.
    """
    return await agent_service.migrate_symlinks()

@router.post("/admin/agents/sync-registry", tags=["Admin"])
async def sync_agents_to_registry(
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
    org_id: Optional[str] = Query(default=None, description="Stamp this org_id on synced rows that have none"),
):
    """Sync all gateway/disk agents into the DB registry.
    
    Idempotent — skips agents already present. Pass ?org_id= to backfill
    org ownership on unscoped legacy agents.
    """
    return await agent_service.sync_agents_to_registry(org_id=org_id)


# ── Chat ────────────────────────────────────────────────────────────────────────

_CHAT_OPENAPI_EXTRA: dict = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["message", "agent_id", "user_id"],
                    "properties": {
                        "message":        {"type": "string", "description": "The user message to send to the agent."},
                        "agent_id":       {"type": "string", "description": "Target agent identifier."},
                        "user_id":        {"type": "string", "description": "Caller's user identifier."},
                        "history":        {
                            "type": "array",
                            "default": [],
                            "description": "Previous messages for context.",
                            "items": {
                                "type": "object",
                                "required": ["role", "content"],
                                "properties": {
                                    "role":    {"type": "string"},
                                    "content": {"type": "string"},
                                },
                            },
                        },
                        "session_id":     {"type": "string", "nullable": True, "description": "Optional session id for DM isolation."},
                        "room_id":        {"type": "string", "nullable": True, "description": "Room id for group @mention chats."},
                        "recent_context": {"type": "string", "nullable": True, "description": "Recent conversation context for group chats."},
                    },
                },
            },
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["message", "agent_id", "user_id"],
                    "properties": {
                        "message":        {"type": "string"},
                        "agent_id":       {"type": "string"},
                        "user_id":        {"type": "string"},
                        "history":        {"type": "string", "description": "JSON-encoded array of {role, content} objects."},
                        "session_id":     {"type": "string"},
                        "room_id":        {"type": "string"},
                        "recent_context": {"type": "string"},
                        "files":          {
                            "type": "array",
                            "items": {"type": "string", "format": "binary"},
                            "description": "Files to upload (images auto-compressed).",
                        },
                    },
                },
            },
        },
    },
}


@router.post("/chat", tags=["Chat"], openapi_extra=_CHAT_OPENAPI_EXTRA)
async def chat(
    request: Request,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    db: Session = Depends(get_db),
):
    """Send a message to an agent. Returns a streaming SSE response."""
    req, file_paths = await parse_chat_request(request)
    return await chat_service.chat_stream(req, uploaded_file_paths=file_paths, db=db)


@router.post("/chat/completions", tags=["Chat"], openapi_extra=_CHAT_OPENAPI_EXTRA)
async def chat_completions(
    request: Request,
    background_tasks: BackgroundTasks,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    db: Session = Depends(get_db),
):
    """Send a message and get the full response (non-streaming)."""
    req, file_paths = await parse_chat_request(request)
    return await chat_service.chat_non_stream(req, background_tasks=background_tasks, uploaded_file_paths=file_paths, db=db)


@router.post("/chat/new-session", tags=["Chat"])
async def new_session(
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    """Generate a new session ID (timestamp-based)."""
    return chat_service.new_session()


# ── Sessions ────────────────────────────────────────────────────────────────────

@router.get("/agents/{agent_id}/sessions", tags=["Sessions"])
async def list_sessions(
    agent_id: str,
    user_id: str | None = None,
    room_id: str | None = None,
    session_service: Annotated[SessionService, Depends(get_session_service)] = None,
):
    """List sessions for a specific agent. Filter by user_id (DM) or room_id (group)."""
    return await session_service.list_sessions(agent_id, user_id=user_id, room_id=room_id)


@router.get("/sessions", tags=["Sessions"])
async def list_all_sessions(
    user_id: str | None = None,
    session_service: Annotated[SessionService, Depends(get_session_service)] = None,
):
    """List all sessions across all agents. Optionally filter by user_id."""
    return await session_service.list_all_sessions(user_id=user_id)


@router.get("/agents/{agent_id}/sessions/{user_id}/history", tags=["Sessions"])
async def get_session_history(
    agent_id: str,
    user_id: str,
    session_id: str | None = None,
    limit: int = 50,
    session_service: Annotated[SessionService, Depends(get_session_service)] = None,
):
    """Get chat history for a specific user DM session."""
    return await session_service.get_session_history(
        agent_id, user_id=user_id, session_id=session_id, limit=limit,
    )


@router.get("/agents/{agent_id}/rooms/{room_id}/history", tags=["Sessions"])
async def get_room_history(
    agent_id: str,
    room_id: str,
    limit: int = 50,
    session_service: Annotated[SessionService, Depends(get_session_service)] = None,
):
    """Get chat history for a group room session."""
    return await session_service.get_session_history(
        agent_id, room_id=room_id, limit=limit,
    )


@router.delete("/agents/{agent_id}/memory", tags=["Sessions"])
async def clear_memory(
    agent_id: str,
    session_service: Annotated[SessionService, Depends(get_session_service)] = None,
):
    """Clear an agent's persistent memory (MEMORY.md)."""
    return await session_service.clear_agent_memory(agent_id)



# ── Cron Jobs ──────────────────────────────────────────────────────────────────

@router.post("/crons", tags=["Cron Jobs"], status_code=201)
async def create_cron(
    req: CreateCronRequest,
    cron_service: Annotated[CronService, Depends(get_cron_service)],
):
    """Create a new cron job."""
    job_id = await cron_service.create_cron(req)
    return {"job_id": job_id, "status": "created"}


@router.get("/crons", tags=["Cron Jobs"], response_model=list[CronResponse])
async def list_crons(
    cron_service: Annotated[CronService, Depends(get_cron_service)],
    db: Session = Depends(get_db),
    user_id: str | None = None,
    session_id: str | None = None,
    agent_id: Optional[str] = Query(default=None, description="Filter by a specific agent"),
    org_id: Optional[str] = Query(default=None, description="Filter by org (ignored if agent_id is set)"),
):
    return await cron_service.list_crons(
        user_id=user_id,
        session_id=session_id,
        org_id=org_id,
        agent_id=agent_id,
        db=db,
    )


@router.get("/crons/{job_id}", tags=["Cron Jobs"], response_model=CronResponse)
async def get_cron(
    job_id: str,
    cron_service: Annotated[CronService, Depends(get_cron_service)],
):
    """Get details for a single cron job."""
    return await cron_service.get_cron(job_id)


@router.patch("/crons/{job_id}", tags=["Cron Jobs"])
async def update_cron(
    job_id: str,
    req: UpdateCronRequest,
    cron_service: Annotated[CronService, Depends(get_cron_service)],
):
    """Update an existing cron job's schedule, payload, or enabled state."""
    return await cron_service.update_cron(job_id, req)


@router.delete("/crons/{job_id}", tags=["Cron Jobs"])
async def delete_cron(
    job_id: str,
    cron_service: Annotated[CronService, Depends(get_cron_service)],
):
    """Delete a cron job."""
    await cron_service.delete_cron(job_id)
    return {"status": "deleted", "job_id": job_id}


@router.post("/crons/{job_id}/trigger", tags=["Cron Jobs"])
async def trigger_cron(
    job_id: str,
    cron_service: Annotated[CronService, Depends(get_cron_service)],
):
    """Manually trigger a cron job to run immediately."""
    return await cron_service.trigger_cron(job_id)


@router.get("/crons/{job_id}/runs", tags=["Cron Jobs"])
async def get_cron_runs(
    job_id: str,
    cron_service: Annotated[CronService, Depends(get_cron_service)],
    limit: int = 20,
):
    """Get the run history for a cron job."""
    return await cron_service.get_cron_runs(job_id, limit=limit)


@router.get("/crons/{job_id}/detail", tags=["Cron Jobs"])
async def get_cron_detail(
    job_id: str,
    cron_service: Annotated[CronService, Depends(get_cron_service)],
):
    """Get the enriched cron job along with parsed run history."""
    job = await cron_service.get_cron(job_id)
    runs = await cron_service.get_cron_runs(job_id, limit=20)
    
    template_tasks = {}
    if job.pipeline_template and isinstance(job.pipeline_template, dict):
        for t in job.pipeline_template.get("tasks", []):
            if "name" in t:
                template_tasks[t["name"]] = t.get("description", "")
                
    for run in runs:
        if run.get("tasks"):
            for task in run["tasks"]:
                task_name = task.get("name")
                if task_name in template_tasks:
                    task["description"] = template_tasks[task_name]
                
    return {
        "job": job.model_dump(),
        "runs": runs
    }


@router.post("/internal/cron-webhook", tags=["Internal"])
async def cron_webhook_receiver(
    req: Request,
    background_tasks: BackgroundTasks,
    usage_service: Annotated[UsageService, Depends(get_usage_service)],
    db: Session = Depends(get_db),
):
    """Receive webhook from OpenClaw when a cron job finishes."""
    payload = await req.json()
    logger.info(f"WEBHOOK PAYLOAD: {json.dumps(payload, indent=2)}")

    job_id = payload.get("jobId") or payload.get("job_id") or payload.get("id")
    if not job_id:
        logger.warning("Cron webhook ignored: No jobId found in payload.")
        return {"status": "ignored"}
        
    status_raw = payload.get("status") or payload.get("job_status", "")
    summary = payload.get("summary", "")
    
    base_status = "success" if str(status_raw).lower() in ("ok", "success") else "error"
    
    tasks = []
    global_int = []
    global_ctx = []
    pipeline_status = base_status
    run_summary = None
    
    match = re.search(r"```pipeline_result\n(.*?)\n```", summary, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(1))
            tasks = parsed.get("tasks", [])
            global_int = parsed.get("global_integrations", [])
            global_ctx = parsed.get("global_context_sources", [])
            pipeline_status = parsed.get("pipeline_status", base_status)
            run_summary = parsed.get("summary")
        except json.JSONDecodeError:
            pipeline_status = "parse_error"  # visible in UI
            run_summary = f"Failed to parse pipeline_result block. Raw: {summary[:500]}"
    else:
        pipeline_status = "parse_error"
        run_summary = f"No pipeline_result block found. Raw: {summary[:500]}"
            
    from ..repositories.cron_pipeline_repository import CronPipelineRepository
    repo = CronPipelineRepository(db)

    run_at = payload.get("runAtMs") or payload.get("run_at_ms") or 0
    duration = payload.get("durationMs") or payload.get("duration_ms") or 0
    finished_at = (int(run_at) + int(duration)) if run_at else None
    
    session_key = payload.get('sessionKey') or payload.get('sessionId') or payload.get('session_key') or payload.get('session_id') or job_id
    run_id = f"{session_key}-{finished_at}"
    
    usage = payload.get("usage", {})
    run_data = {
        "id": run_id,
        "cron_id": job_id,
        "status": pipeline_status,
        "started_at": run_at,
        "finished_at": finished_at,
        "duration_ms": duration,
        "tasks": tasks,
        "global_integrations": global_int,
        "global_context_sources": global_ctx,
        "raw_summary": summary,
        "summary": run_summary,
        "model": payload.get("model"),
        "input_tokens": usage.get("input_tokens") or usage.get("inputTokens"),
        "output_tokens": usage.get("output_tokens") or usage.get("outputTokens"),
    }
    
    try:
        repo.insert_run(run_data)

        # Trigger cost sync from session log
        # sessionKey format: agent:<agent_id>:cron:...
        agent_id = None
        if str(session_key).startswith("agent:"):
            parts = str(session_key).split(":")
            if len(parts) > 1:
                agent_id = parts[1]
        
        session_id = payload.get("sessionId") or payload.get("session_id")
        if agent_id and session_id:
            background_tasks.add_task(usage_service.sync_cron_cost, agent_id, session_id, run_id)

        # Deduct cost from wallet after cron cost sync
        from ..repositories.cron_ownership_repository import CronOwnershipRepository as OwnerRepoWallet
        _owner_wallet = OwnerRepoWallet(db).get(job_id)
        if _owner_wallet:
            background_tasks.add_task(usage_service.deduct_cron_run_cost, run_id, _owner_wallet["user_id"])

        # Broadcast the new run to Websocket if needed
        from ..ws_manager import cron_ws_manager
        import asyncio
        asyncio.create_task(cron_ws_manager.broadcast("cron_run_finished", {"job_id": job_id, "run": run_data}))

        # Log to unified activity stream
        if agent_id:
            from ..services.agent_activity_service import log_activity_sync
            duration_s = round(int(duration) / 1000, 1) if duration else 0
            activity_summary = f"Cron job completed: {job_id} ({pipeline_status}, {duration_s}s)"
            if run_summary:
                activity_summary += f" — {run_summary[:100]}"
            log_activity_sync(
                db, agent_id, "cron_run_completed", activity_summary,
                metadata={
                    "job_id": job_id,
                    "pipeline_status": pipeline_status,
                    "duration_ms": duration,
                    "tasks_count": len(tasks),
                    "model": payload.get("model"),
                },
                status="success" if pipeline_status == "success" else "error",
            )

        # Send summary to Garage chat (strip pipeline_result block)
        from ..tools.garage_tool import send_cron_summary_to_chat
        from ..repositories.cron_ownership_repository import CronOwnershipRepository as OwnerRepo
        owner_repo = OwnerRepo(db)
        owner = owner_repo.get(job_id)
        if not owner:
            logger.warning("No cron ownership found for job %s — skipping chat delivery", job_id)
        elif owner:
            clean_summary = re.sub(r"```pipeline_result\n.*?\n```", "", summary, flags=re.DOTALL).strip()
            chat_msg = f"{clean_summary or run_summary or 'Task completed.'}"
            logger.info("Sending cron summary to chat for job %s (user=%s, agent=%s)", job_id, owner["user_id"], owner["agent_id"])
            asyncio.create_task(
                send_cron_summary_to_chat(
                    user_id=owner["user_id"],
                    session_id=owner["session_id"],
                    agent_id=owner["agent_id"],
                    summary=chat_msg,
                )
            )

    except Exception as e:
        logger.error(f"Failed to process cron webhook: {e}")
        
    return {"status": "ok"}



# ── Tasks (AI Kanban) ──────────────────────────────────────────────────────────

@router.post("/tasks", tags=["Tasks"], status_code=201, response_model=TaskResponse)
async def create_task(
    req: CreateTaskRequest,
    task_service: Annotated[TaskService, Depends(get_task_service)],
):
    """Create a new agent task."""
    return await task_service.create_task(req)


@router.get("/tasks", tags=["Tasks"], response_model=list[TaskResponse])
async def list_tasks(
    task_service: Annotated[TaskService, Depends(get_task_service)],
    agent_id: str | None = None,
    user_id: str | None = None,
    status: str | None = None,
    org_id: Optional[str] = Query(default=None, description="Filter tasks by org (ignored if agent_id is set)"),
):
    return await task_service.list_tasks(agent_id=agent_id, user_id=user_id, status=status, org_id=org_id)


@router.get("/tasks/{task_id}", tags=["Tasks"], response_model=TaskResponse)
async def get_task(
    task_id: str,
    task_service: Annotated[TaskService, Depends(get_task_service)],
):
    """Get a single task by ID."""
    return await task_service.get_task(task_id)


@router.patch("/tasks/{task_id}", tags=["Tasks"], response_model=TaskResponse)
async def update_task(
    task_id: str,
    req: UpdateTaskRequest,
    task_service: Annotated[TaskService, Depends(get_task_service)],
):
    """Update a task (status, sub-tasks, issues, etc.)."""
    return await task_service.update_task(task_id, req)


@router.delete("/tasks/{task_id}", tags=["Tasks"])
async def delete_task(
    task_id: str,
    task_service: Annotated[TaskService, Depends(get_task_service)],
):
    """Delete a task."""
    return await task_service.delete_task(task_id)


@router.patch("/tasks/{task_id}/issues/{issue_index}/resolve", tags=["Tasks"], response_model=TaskResponse)
async def resolve_issue(
    task_id: str,
    issue_index: int,
    task_service: Annotated[TaskService, Depends(get_task_service)],
):
    """Mark a specific issue on a task as resolved (by the human)."""
    return await task_service.resolve_issue(task_id, issue_index)
