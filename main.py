"""OpenClaw API — Unified Agent Manager & Service Gateway."""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent_manager.config import settings
from agent_manager.router import router as agent_router
from gmail_service.router import router as gmail_router

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
        "- **Agent Manager**: `/agent-manager/api/...`\n"
        "- **Gmail Service**: `/gmail-auth/auth/...`, `/gmail-auth/email/...`"
    ),
    version="1.0.0",
    lifespan=lifespan,
    # The root_path might need to be adjusted if behind proxy, but for now we follow config
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

# Agent Manager endpoints: /agent-manager/...
# Note: agent_manager/router.py likely defines paths starting with /api/...,
# so combined path will be /agent-manager/api/... which is fine.
app.include_router(
    agent_router,
    prefix="/agent-manager",
    tags=["Agent Manager"],
    responses={404: {"description": "Agent or resource not found"}},
)

# Gmail Service endpoints: /gmail-auth/...
# Note: gmail_service/router.py likely defines paths starting with /auth/...,
# so combined path will be /gmail-auth/auth/... which matches requirements.
app.include_router(
    gmail_router,
    prefix="/gmail-auth",
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
