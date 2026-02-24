"""OpenClaw AgentManager — FastAPI application entry-point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent_manager import agent_service, chat_service, session_service
from agent_manager.config import settings
from agent_manager.openclaw import run_openclaw
from agent_manager.schemas import (
    ChatRequest,
    CreateAgentRequest,
    HealthResponse,
    UpdateAgentRequest,
)
from agent_manager.chat_helpers import parse_chat_request

# ── Logging ─────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("agent_manager")


# ── Lifespan ────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "AgentManager starting — gateway=%s  state_dir=%s",
        settings.OPENCLAW_GATEWAY_URL,
        settings.OPENCLAW_STATE_DIR,
    )
    yield
    logger.info("AgentManager shutting down")


# ── App ─────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="OpenClaw AgentManager",
    description=(
        "REST API for programmatic management of OpenClaw agents. "
        "Wraps CLI commands and proxies chat to the OpenClaw Gateway."
    ),
    version="1.0.0",
    lifespan=lifespan,
    root_path=settings.ROOT_PATH,
)


# ── Global exception handler ───────────────────────────────────────────────────

@app.exception_handler(Exception)
async def _unhandled_exception(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": str(exc),
            "error": type(exc).__name__,
            "path": str(request.url.path),
            "method": request.method,
        },
    )


# ── Health ──────────────────────────────────────────────────────────────────────

@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
async def health():
    """Return gateway status, agent count, and server version."""
    gateway_ok = False
    gateway_status: Any = None
    try:
        gateway_status = await run_openclaw(["gateway", "status", "--json"])
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

    # Determine overall status based on component health
    if gateway_ok:
        overall = "ok"
    else:
        overall = "degraded"  # server is up but gateway is unreachable

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

@app.post("/api/agents", tags=["Agents"], status_code=201)
async def create_agent(req: CreateAgentRequest):
    """Create a new OpenClaw agent (filesystem + gateway registration)."""
    return await agent_service.create_agent(req)


@app.get("/api/agents", tags=["Agents"])
async def list_agents():
    """List all registered agents."""
    return await agent_service.list_agents()


@app.get("/api/agents/{agent_id}", tags=["Agents"])
async def get_agent(agent_id: str):
    """Get details for a single agent."""
    return await agent_service.get_agent(agent_id)


@app.patch("/api/agents/{agent_id}", tags=["Agents"])
async def update_agent(agent_id: str, req: UpdateAgentRequest):
    """Update an agent's identity, role, or personality files."""
    return await agent_service.update_agent(agent_id, req)


@app.delete("/api/agents/{agent_id}", tags=["Agents"])
async def delete_agent(agent_id: str):
    """Delete an agent (gateway de-registration + filesystem cleanup)."""
    return await agent_service.delete_agent(agent_id)


# ── Chat ────────────────────────────────────────────────────────────────────────

# OpenAPI schema shared by both chat endpoints so Swagger shows the full
# request body for JSON **and** multipart (with file uploads).
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


@app.post("/api/chat", tags=["Chat"], openapi_extra=_CHAT_OPENAPI_EXTRA)
async def chat(request: Request):
    """Send a message to an agent. Returns a streaming SSE response.

    Accepts either:
    - **JSON body**: `{"message": ..., "agent_id": ..., "user_id": ..., ...}`
    - **Multipart form**: form fields + optional `files` for file uploads.
    """
    req, file_paths = await parse_chat_request(request)
    return await chat_service.chat_stream(req, uploaded_file_paths=file_paths)


@app.post("/api/chat/completions", tags=["Chat"], openapi_extra=_CHAT_OPENAPI_EXTRA)
async def chat_completions(request: Request):
    """Send a message and get the full response (non-streaming).

    Accepts either:
    - **JSON body**: `{"message": ..., "agent_id": ..., "user_id": ..., ...}`
    - **Multipart form**: form fields + optional `files` for file uploads.
    """
    req, file_paths = await parse_chat_request(request)
    return await chat_service.chat_non_stream(req, uploaded_file_paths=file_paths)


@app.post("/api/chat/new-session", tags=["Chat"])
async def new_session():
    """Generate a new session ID (timestamp-based)."""
    return chat_service.new_session()


# ── Sessions ────────────────────────────────────────────────────────────────────

@app.get("/api/agents/{agent_id}/sessions", tags=["Sessions"])
async def list_sessions(
    agent_id: str,
    user_id: str | None = None,
    room_id: str | None = None,
):
    """List sessions for a specific agent. Filter by user_id (DM) or room_id (group)."""
    return await session_service.list_sessions(agent_id, user_id=user_id, room_id=room_id)


@app.get("/api/sessions", tags=["Sessions"])
async def list_all_sessions(user_id: str | None = None):
    """List all sessions across all agents. Optionally filter by user_id."""
    return await session_service.list_all_sessions(user_id=user_id)


@app.get("/api/agents/{agent_id}/sessions/{user_id}/history", tags=["Sessions"])
async def get_session_history(
    agent_id: str,
    user_id: str,
    session_id: str | None = None,
    limit: int = 50,
):
    """Get chat history for a specific user DM session."""
    return await session_service.get_session_history(
        agent_id, user_id=user_id, session_id=session_id, limit=limit,
    )


@app.get("/api/agents/{agent_id}/rooms/{room_id}/history", tags=["Sessions"])
async def get_room_history(
    agent_id: str,
    room_id: str,
    limit: int = 50,
):
    """Get chat history for a group room session."""
    return await session_service.get_session_history(
        agent_id, room_id=room_id, limit=limit,
    )


@app.delete("/api/agents/{agent_id}/memory", tags=["Sessions"])
async def clear_memory(agent_id: str):
    """Clear an agent's persistent memory (MEMORY.md).

    Use a new session_id in subsequent chat requests for a fully clean slate.
    """
    return await session_service.clear_agent_memory(agent_id)


# ── Entry-point ─────────────────────────────────────────────────────────────────

def main():
    uvicorn.run(
        "main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
