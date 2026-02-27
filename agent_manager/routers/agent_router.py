"""AgentManager router — agents, chat, sessions, cron."""

from __future__ import annotations

import logging
from typing import Any, Annotated

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse

from ..config import settings
from ..schemas.chat import (
    ChatRequest,
    CreateAgentRequest,
    HealthResponse,
    UpdateAgentRequest,
    CreateSkillRequest,
    UpdateSkillRequest,
    SkillResponse,
    SkillListResponse,
)
from ..schemas.cron import CreateCronRequest, UpdateCronRequest, CronResponse
from ..schemas.task import CreateTaskRequest, UpdateTaskRequest, TaskResponse
from ..chat_helpers import parse_chat_request
from ..dependencies import (
    get_agent_service, get_session_service, get_chat_service, get_gateway,
    get_skill_service, get_cron_service, get_task_service,
)
from ..services.agent_service import AgentService
from ..services.session_service import SessionService
from ..services.chat_service import ChatService
from ..services.skill_service import SkillService
from ..services.cron_service import CronService
from ..services.task_service import TaskService
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


# ── Agent CRUD ──────────────────────────────────────────────────────────────────

@router.post("/agents", tags=["Agents"], status_code=201)
async def create_agent(
    req: CreateAgentRequest,
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """Create a new OpenClaw agent (filesystem + gateway registration)."""
    return await agent_service.create_agent(req)


@router.get("/agents", tags=["Agents"])
async def list_agents(
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """List all registered agents."""
    return await agent_service.list_agents()


@router.get("/agents/{agent_id}", tags=["Agents"])
async def get_agent(
    agent_id: str,
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """Get details for a single agent."""
    return await agent_service.get_agent(agent_id)


@router.patch("/agents/{agent_id}", tags=["Agents"])
async def update_agent(
    agent_id: str,
    req: UpdateAgentRequest,
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """Update an agent's identity, role, or personality files."""
    return await agent_service.update_agent(agent_id, req)


@router.delete("/agents/{agent_id}", tags=["Agents"])
async def delete_agent(
    agent_id: str,
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """Delete an agent (gateway de-registration + filesystem cleanup)."""
    return await agent_service.delete_agent(agent_id)


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
):
    """Send a message to an agent. Returns a streaming SSE response."""
    req, file_paths = await parse_chat_request(request)
    return await chat_service.chat_stream(req, uploaded_file_paths=file_paths)


@router.post("/chat/completions", tags=["Chat"], openapi_extra=_CHAT_OPENAPI_EXTRA)
async def chat_completions(
    request: Request,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    """Send a message and get the full response (non-streaming)."""
    req, file_paths = await parse_chat_request(request)
    return await chat_service.chat_non_stream(req, uploaded_file_paths=file_paths)


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


# ── Skills ──────────────────────────────────────────────────────────────────────

@router.post("/skills", tags=["Skills"], status_code=201, response_model=SkillResponse)
async def create_skill(
    req: CreateSkillRequest,
    skill_service: Annotated[SkillService, Depends(get_skill_service)],
):
    """Create a new skill. name becomes the folder slug (kebab-case)."""
    return await skill_service.create_skill(req)


@router.get("/skills", tags=["Skills"], response_model=SkillListResponse)
async def list_skills(
    skill_service: Annotated[SkillService, Depends(get_skill_service)],
):
    """List all installed skill slugs."""
    return await skill_service.list_skills()


@router.get("/skills/{skill_name}", tags=["Skills"], response_model=SkillResponse)
async def get_skill(
    skill_name: str,
    skill_service: Annotated[SkillService, Depends(get_skill_service)],
):
    """Get metadata for a specific skill."""
    return await skill_service.get_skill(skill_name)


@router.get("/skills/{skill_name}/content", tags=["Skills"])
async def get_skill_content(
    skill_name: str,
    skill_service: Annotated[SkillService, Depends(get_skill_service)],
):
    """Get the raw SKILL.md content for a specific skill."""
    content = await skill_service.get_skill_content(skill_name)
    return {"name": skill_name, "content": content}


@router.patch("/skills/{skill_name}", tags=["Skills"], response_model=SkillResponse)
async def update_skill(
    skill_name: str,
    req: UpdateSkillRequest,
    skill_service: Annotated[SkillService, Depends(get_skill_service)],
):
    """Update the SKILL.md content for an existing skill."""
    return await skill_service.update_skill(skill_name, req)


@router.delete("/skills/{skill_name}", tags=["Skills"])
async def delete_skill(
    skill_name: str,
    skill_service: Annotated[SkillService, Depends(get_skill_service)],
):
    """Delete a skill and its directory."""
    return await skill_service.delete_skill(skill_name)


# ── Agent-scoped Skills ─────────────────────────────────────────────────────────

@router.get("/agents/{agent_id}/skills/status", tags=["Agent Skills"])
async def get_skills_status(
    agent_id: str,
    skill_service: Annotated[SkillService, Depends(get_skill_service)],
):
    """List all global skills with an `installed` flag for this agent."""
    skills = await skill_service.list_skills_with_status(agent_id)
    return {"agent_id": agent_id, "skills": skills, "count": len(skills)}


@router.post("/agents/{agent_id}/skills/install/{skill_name}", tags=["Agent Skills"], status_code=201, response_model=SkillResponse)
async def install_global_skill(
    agent_id: str,
    skill_name: str,
    skill_service: Annotated[SkillService, Depends(get_skill_service)],
):
    """Install a globally-available skill into this agent's workspace by name."""
    return await skill_service.install_global_skill(agent_id, skill_name)


@router.post("/agents/{agent_id}/skills", tags=["Agent Skills"], status_code=201, response_model=SkillResponse)
async def create_agent_skill(
    agent_id: str,
    req: CreateSkillRequest,
    skill_service: Annotated[SkillService, Depends(get_skill_service)],
):
    """Create a custom skill directly in this agent's workspace."""
    return await skill_service.create_agent_skill(agent_id, req)


@router.get("/agents/{agent_id}/skills", tags=["Agent Skills"], response_model=SkillListResponse)
async def list_agent_skills(
    agent_id: str,
    skill_service: Annotated[SkillService, Depends(get_skill_service)],
):
    """List all skills installed for a specific agent."""
    return await skill_service.list_agent_skills(agent_id)


@router.get("/agents/{agent_id}/skills/{skill_name}", tags=["Agent Skills"], response_model=SkillResponse)
async def get_agent_skill(
    agent_id: str,
    skill_name: str,
    skill_service: Annotated[SkillService, Depends(get_skill_service)],
):
    """Get metadata for a specific agent skill."""
    return await skill_service.get_agent_skill(agent_id, skill_name)


@router.get("/agents/{agent_id}/skills/{skill_name}/content", tags=["Agent Skills"])
async def get_agent_skill_content(
    agent_id: str,
    skill_name: str,
    skill_service: Annotated[SkillService, Depends(get_skill_service)],
):
    """Get the raw SKILL.md content for a specific agent skill."""
    content = await skill_service.get_agent_skill_content(agent_id, skill_name)
    return {"agent_id": agent_id, "name": skill_name, "content": content}


@router.patch("/agents/{agent_id}/skills/{skill_name}", tags=["Agent Skills"], response_model=SkillResponse)
async def update_agent_skill(
    agent_id: str,
    skill_name: str,
    req: UpdateSkillRequest,
    skill_service: Annotated[SkillService, Depends(get_skill_service)],
):
    """Update the SKILL.md content for an agent-specific skill."""
    return await skill_service.update_agent_skill(agent_id, skill_name, req)


@router.delete("/agents/{agent_id}/skills/{skill_name}", tags=["Agent Skills"])
async def delete_agent_skill(
    agent_id: str,
    skill_name: str,
    skill_service: Annotated[SkillService, Depends(get_skill_service)],
):
    """Remove a skill from a specific agent's workspace."""
    return await skill_service.delete_agent_skill(agent_id, skill_name)


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
    user_id: str | None = None,
    session_id: str | None = None,
):
    """List cron jobs. Optionally filter by user_id and/or session_id."""
    return await cron_service.list_crons(user_id=user_id, session_id=session_id)


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
    status: str | None = None,
):
    """List tasks. Optionally filter by agent_id and/or status."""
    return await task_service.list_tasks(agent_id=agent_id, status=status)


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
