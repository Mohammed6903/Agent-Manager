"""OpenClaw API — Unified Agent Manager & Service Gateway."""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent_manager.config import settings
from agent_manager.routers.agent_router import router as agent_router
from agent_manager.routers.gmail_router import router as gmail_router

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
    tags=["Agent Manager"],
    responses={404: {"description": "Agent or resource not found"}},
)

# Gmail Service endpoints: /api/gmail/auth, /api/gmail/email, /api/gmail/calendar, etc.
app.include_router(
    gmail_router,
    prefix="/api/gmail",
    tags=["Gmail Service"],
    responses={404: {"description": "Resource not found"}},
)


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
