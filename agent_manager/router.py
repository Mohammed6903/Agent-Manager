"""AgentManager router."""

from __future__ import annotations

import logging
from typing import Any, Annotated

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse

from .config import settings
from .schemas import (
    ChatRequest,
    CreateAgentRequest,
    HealthResponse,
    UpdateAgentRequest,
)
from .chat_helpers import parse_chat_request
from .dependencies import get_agent_service, get_session_service, get_chat_service, get_gateway
from .services.agent_service import AgentService
from .services.session_service import SessionService
from .services.chat_service import ChatService
from .clients.gateway_client import GatewayClient

logger = logging.getLogger("agent_manager")

router = APIRouter()

# ── Health ──────────────────────────────────────────────────────────────────────

@router.get("/api/health", response_model=HealthResponse, tags=["Health"])
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

@router.post("/api/agents", tags=["Agents"], status_code=201)
async def create_agent(
    req: CreateAgentRequest,
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """Create a new OpenClaw agent (filesystem + gateway registration)."""
    return await agent_service.create_agent(req)


@router.get("/api/agents", tags=["Agents"])
async def list_agents(
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """List all registered agents."""
    return await agent_service.list_agents()


@router.get("/api/agents/{agent_id}", tags=["Agents"])
async def get_agent(
    agent_id: str,
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """Get details for a single agent."""
    return await agent_service.get_agent(agent_id)


@router.patch("/api/agents/{agent_id}", tags=["Agents"])
async def update_agent(
    agent_id: str,
    req: UpdateAgentRequest,
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """Update an agent's identity, role, or personality files."""
    return await agent_service.update_agent(agent_id, req)


@router.delete("/api/agents/{agent_id}", tags=["Agents"])
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


@router.post("/api/chat", tags=["Chat"], openapi_extra=_CHAT_OPENAPI_EXTRA)
async def chat(
    request: Request,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    """Send a message to an agent. Returns a streaming SSE response."""
    req, file_paths = await parse_chat_request(request)
    return await chat_service.chat_stream(req, uploaded_file_paths=file_paths)


@router.post("/api/chat/completions", tags=["Chat"], openapi_extra=_CHAT_OPENAPI_EXTRA)
async def chat_completions(
    request: Request,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    """Send a message and get the full response (non-streaming)."""
    req, file_paths = await parse_chat_request(request)
    return await chat_service.chat_non_stream(req, uploaded_file_paths=file_paths)


@router.post("/api/chat/new-session", tags=["Chat"])
async def new_session(
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    """Generate a new session ID (timestamp-based)."""
    return chat_service.new_session()


# ── Sessions ────────────────────────────────────────────────────────────────────

@router.get("/api/agents/{agent_id}/sessions", tags=["Sessions"])
async def list_sessions(
    agent_id: str,
    user_id: str | None = None,
    room_id: str | None = None,
    session_service: Annotated[SessionService, Depends(get_session_service)] = None,
):
    """List sessions for a specific agent. Filter by user_id (DM) or room_id (group)."""
    return await session_service.list_sessions(agent_id, user_id=user_id, room_id=room_id)


@router.get("/api/sessions", tags=["Sessions"])
async def list_all_sessions(
    user_id: str | None = None,
    session_service: Annotated[SessionService, Depends(get_session_service)] = None,
):
    """List all sessions across all agents. Optionally filter by user_id."""
    return await session_service.list_all_sessions(user_id=user_id)


@router.get("/api/agents/{agent_id}/sessions/{user_id}/history", tags=["Sessions"])
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


@router.get("/api/agents/{agent_id}/rooms/{room_id}/history", tags=["Sessions"])
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


@router.delete("/api/agents/{agent_id}/memory", tags=["Sessions"])
async def clear_memory(
    agent_id: str,
    session_service: Annotated[SessionService, Depends(get_session_service)] = None,
):
    """Clear an agent's persistent memory (MEMORY.md)."""
    return await session_service.clear_agent_memory(agent_id)
