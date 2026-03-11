"""OpenClaw API — Unified Agent Manager & Service Gateway."""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent_manager.config import settings
from agent_manager.routers.agent_router import router as agent_router
from agent_manager.routers.google_auth_router import router as google_auth_router
from agent_manager.routers.gmail_router import router as gmail_router
from agent_manager.routers.calendar_router import router as calendar_router
from agent_manager.routers.drive_router import router as drive_router
from agent_manager.routers.sheets_router import router as sheets_router
from agent_manager.routers.docs_router import router as docs_router
from agent_manager.routers.secrets_router import router as secrets_router
from agent_manager.routers.garage_router import router as garage_router
from agent_manager.routers.context_router import router as context_router
from agent_manager.routers.integration_router import router as integration_router
from agent_manager.routers.twitter_router import router as twitter_router
from agent_manager.routers.cron_template_router import router as cron_template_router
from agent_manager.routers.analytics_router import router as analytics_router
from agent_manager.routers.third_party_context_router import router as third_party_context_router
from agent_manager.ws_manager import task_ws_manager, cron_ws_manager
from agent_manager.dependencies import get_storage, get_gateway
from agent_manager.services.qdrant_service import ensure_collection

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

    # Ensure Qdrant collection
    try:
        ensure_collection()
        logger.info("Qdrant collection ensured")
    except Exception as exc:
        logger.warning("Failed to ensure Qdrant collection: %s", exc)

    # Bootstrap shared workspace files (SOUL.md, AGENTS.md)
    try:
        from agent_manager.services.agent_service import AgentService
        svc = AgentService(get_storage(), get_gateway())
        await svc.ensure_shared_files()
        result = await svc.sync_templates_to_shared()
        logger.info("Shared workspace files synced from source templates: %s", result)
    except Exception as exc:
        logger.warning("Failed to bootstrap/sync shared files: %s", exc)

    yield
    # Log shutdown
    logger.info("OpenClaw API shutting down")


# ── App ─────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="OpenClaw API",
    description=(
        "Unified API for OpenClaw Agent Management.\n\n"
        "- **Integrations (Gmail, Calendar, etc)**: `/api/integrations/...`\n"
        "- **Secrets**: `/api/secrets/...`"
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

# Agent Manager endpoints: /api/health, /api/agents, /api/chat, /api/tasks, etc.
app.include_router(
    agent_router,
    prefix="/api",
    responses={404: {"description": "Agent or resource not found"}},
)

# Google Auth endpoints
app.include_router(
    google_auth_router,
    prefix="/api/integrations/google/auth",
    responses={404: {"description": "Resource not found"}},
)

# Gmail endpoints
app.include_router(
    gmail_router,
    prefix="/api/integrations/gmail",
    responses={404: {"description": "Resource not found"}},
)

# Calendar endpoints
app.include_router(
    calendar_router,
    prefix="/api/integrations/calendar",
    responses={404: {"description": "Resource not found"}},
)

# Drive endpoints
app.include_router(
    drive_router,
    prefix="/api/integrations/drive",
    responses={404: {"description": "Resource not found"}},
)

# Sheets endpoints
app.include_router(
    sheets_router,
    prefix="/api/integrations/sheets",
    responses={404: {"description": "Resource not found"}},
)

# Docs endpoints
app.include_router(
    docs_router,
    prefix="/api/integrations/docs",
    responses={404: {"description": "Resource not found"}},
)

# Secrets endpoint
app.include_router(
    secrets_router,
    prefix="/api/secrets",
    responses={404: {"description": "Resource not found"}},
)

# Garage Feed endpoints: /api/garage/posts, etc.
app.include_router(
    garage_router,
    prefix="/api/garage",
    responses={404: {"description": "Resource not found"}},
)

# Third-party context endpoints: /api/contexts/third-party
# Must be registered before context_router so its literal prefix wins over
# the /{context_id} catch-all route defined in context_router.
app.include_router(
    third_party_context_router,
    prefix="/api/contexts/third-party",
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

# Twitter endpoints
app.include_router(
    twitter_router,
    prefix="/api/integrations/twitter",
    responses={404: {"description": "Resource not found"}},
)

# Cron Template endpoints: /api/cron-templates
app.include_router(
    cron_template_router,
    prefix="/api/cron-templates",
    responses={404: {"description": "Resource not found"}},
)

# Analytics endpoints: /api/analytics
app.include_router(
    analytics_router,
    prefix="/api",
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
