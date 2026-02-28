"""OpenClaw API — Unified Agent Manager & Service Gateway."""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent_manager.config import settings
from agent_manager.routers.agent_router import router as agent_router
from agent_manager.routers.gmail_router import router as gmail_router
from agent_manager.routers.garage_router import router as garage_router
from agent_manager.routers.context_router import router as context_router
from agent_manager.routers.integration_router import router as integration_router
from agent_manager.ws_manager import task_ws_manager, cron_ws_manager

# ── Logging ─────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("openclaw")


# ── Lifespan ────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Log startup
    logger.info(
        "OpenClaw API starting — gateway=%s  state_dir=%s",
        settings.OPENCLAW_GATEWAY_URL,
        settings.OPENCLAW_STATE_DIR,
    )
    yield
    # Log shutdown
    logger.info("OpenClaw API shutting down")


# ── App ─────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="OpenClaw API",
    description=(
        "Unified API for OpenClaw Agent Management AND Gmail Service.\n\n"
        "- **Agents, Chat, Skills**: `/api/...`\n"
        "- **Gmail, Calendar, Secrets**: `/api/gmail/...`"
    ),
    version="1.0.0",
    lifespan=lifespan,
    root_path=settings.ROOT_PATH,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)


# ── CORS ────────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


# ── Routers ─────────────────────────────────────────────────────────────────────

# Agent Manager endpoints: /api/health, /api/agents, /api/chat, /api/skills, etc.
app.include_router(
    agent_router,
    prefix="/api",
    responses={404: {"description": "Agent or resource not found"}},
)

# Gmail Service endpoints: /api/gmail/auth, /api/gmail/email, /api/gmail/calendar, etc.
app.include_router(
    gmail_router,
    prefix="/api/gmail",
    responses={404: {"description": "Resource not found"}},
)

# Garage Feed endpoints: /api/garage/posts, etc.
app.include_router(
    garage_router,
    prefix="/api/garage",
    responses={404: {"description": "Resource not found"}},
)

# Context endpoints: /api/contexts
app.include_router(
    context_router,
    prefix="/api/contexts",
    responses={404: {"description": "Resource not found"}},
)

# Integration endpoints: /api/integrations
app.include_router(
    integration_router,
    prefix="/api/integrations",
    responses={404: {"description": "Resource not found"}},
)


# ── WebSocket ───────────────────────────────────────────────────────────────────

@app.websocket("/api/tasks/ws")
async def tasks_websocket(ws: WebSocket):
    """Real-time task board updates."""
    await task_ws_manager.connect(ws)
    try:
        while True:
            # Keep connection alive; ignore incoming messages
            await ws.receive_text()
    except WebSocketDisconnect:
        task_ws_manager.disconnect(ws)


@app.websocket("/api/crons/ws")
async def crons_websocket(ws: WebSocket):
    """Real-time cron job updates."""
    await cron_ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        cron_ws_manager.disconnect(ws)


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
