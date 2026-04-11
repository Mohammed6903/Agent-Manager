"""OpenClaw API — Unified Agent Manager & Service Gateway."""

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent_manager.config import settings
from agent_manager.routers.agent_router import router as agent_router
from agent_manager.integrations.google.auth.router import router as google_auth_router
from agent_manager.integrations.google.gmail.router import router as gmail_router
from agent_manager.integrations.google.calendar.router import router as calendar_router
from agent_manager.integrations.google.drive.router import router as drive_router
from agent_manager.integrations.google.sheets.router import router as sheets_router
from agent_manager.integrations.google.docs.router import router as docs_router
from agent_manager.integrations.google.slides.router import router as slides_router
from agent_manager.integrations.google.forms.router import router as forms_router
from agent_manager.integrations.google.ads.router import router as ads_router
from agent_manager.integrations.google.youtube.router import router as youtube_router
from agent_manager.integrations.google.analytics.router import router as analytics_intg_router
from agent_manager.integrations.google.search_console.router import router as search_console_router
from agent_manager.routers.secrets_router import router as secrets_router
from agent_manager.routers.garage_router import router as garage_router
from agent_manager.routers.context_router import router as context_router
from agent_manager.routers.integration_router import router as integration_router
from agent_manager.integrations.twitter.router import router as twitter_router
from agent_manager.integrations.linkedin.router import router as linkedin_router
from agent_manager.integrations.notion.router import router as notion_router
from agent_manager.integrations.slack.router import router as slack_router
from agent_manager.integrations.github.router import router as github_router
from agent_manager.integrations.trello.router import router as trello_router
from agent_manager.integrations.airtable.router import router as airtable_router
from agent_manager.integrations.asana.router import router as asana_router
from agent_manager.integrations.clickup.router import router as clickup_router
from agent_manager.integrations.todoist.router import router as todoist_router
from agent_manager.integrations.typeform.router import router as typeform_router
from agent_manager.integrations.stripe.router import router as stripe_router
from agent_manager.integrations.hubspot.router import router as hubspot_router
from agent_manager.integrations.jira.router import router as jira_router
from agent_manager.integrations.salesforce.router import router as salesforce_router
from agent_manager.integrations.monday.router import router as monday_router
from agent_manager.integrations.dropbox.router import router as dropbox_router
from agent_manager.integrations.mailchimp.router import router as mailchimp_router
from agent_manager.integrations.calendly.router import router as calendly_router
from agent_manager.integrations.pipedrive.router import router as pipedrive_router
from agent_manager.integrations.confluence.router import router as confluence_router
from agent_manager.integrations.zohocrm.router import router as zohocrm_router
from agent_manager.integrations.linear.router import router as linear_router
from agent_manager.integrations.box.router import router as box_router
from agent_manager.integrations.buffer.router import router as buffer_router
from agent_manager.integrations.resend.router import router as resend_router
from agent_manager.integrations.sendgrid.router import router as sendgrid_router
from agent_manager.integrations.wrike.router import router as wrike_router
from agent_manager.integrations.eventbrite.router import router as eventbrite_router
from agent_manager.integrations.basecamp.router import router as basecamp_router
from agent_manager.integrations.chargebee.router import router as chargebee_router
from agent_manager.integrations.clockify.router import router as clockify_router
from agent_manager.integrations.quickbooks.router import router as quickbooks_router
from agent_manager.integrations.xero.router import router as xero_router
from agent_manager.integrations.twilio.router import router as twilio_router
from agent_manager.integrations.whatsapp.router import router as whatsapp_router
from agent_manager.voice_call.router import router as voice_call_router
from agent_manager.integrations.telegram.router import router as telegram_router
from agent_manager.integrations.wordpress.router import router as wordpress_router
from agent_manager.integrations.woocommerce.router import router as woocommerce_router
from agent_manager.integrations.square.router import router as square_router
from agent_manager.integrations.sentry.router import router as sentry_router
from agent_manager.integrations.posthog.router import router as posthog_router
from agent_manager.integrations.outlook.router import router as outlook_router
from agent_manager.integrations.microsoft_teams.router import router as microsoft_teams_router
from agent_manager.integrations.onedrive.router import router as onedrive_router
from agent_manager.routers.cron_template_router import router as cron_template_router
from agent_manager.routers.analytics_router import router as analytics_router
from agent_manager.routers.billing_router import router as billing_router
from agent_manager.routers.third_party_context_router import router as third_party_context_router
from agent_manager.ws_manager import task_ws_manager, cron_ws_manager, activity_ws_manager
from agent_manager.routers.agent_activity_router import router as agent_activity_router
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

    # Clean up stale voice calls from previous server sessions. Calls stuck
    # in non-terminal states (initiated, ringing, etc.) for >2 minutes were
    # almost certainly killed by a server restart and should not block the
    # dedup check from placing new calls.
    try:
        from datetime import datetime, timezone, timedelta
        from agent_manager.database import SessionLocal
        from agent_manager.models.voice_call import VoiceCall

        db = SessionLocal()
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=2)
        stale = (
            db.query(VoiceCall)
            .filter(
                VoiceCall.state.in_(["initiated", "ringing", "answered", "speaking", "listening"]),
                VoiceCall.started_at < cutoff,
            )
            .all()
        )
        if stale:
            now = datetime.now(timezone.utc)
            for c in stale:
                c.state = "ended"
                c.end_reason = "stale_cleanup"
                c.ended_at = now
            db.commit()
            logger.info("Cleaned %d stale voice call(s) on startup", len(stale))
        db.close()
    except Exception as exc:
        logger.warning("Failed to clean stale voice calls: %s", exc)

    # Start server-side heartbeat for all agents (every 5s)
    from agent_manager.services.heartbeat_service import start_heartbeat_task
    heartbeat_task = start_heartbeat_task()
    logger.info("Heartbeat service started")

    # Backfill pre-RAG manual contexts in the background. Pre-existing
    # GlobalContext rows created before the RAG pipeline landed have
    # ``content_hash IS NULL`` and no Qdrant chunks. We sweep them on
    # startup so search starts working without operator intervention.
    # Runs in a background task (not awaited) because embedding many
    # documents can take a while on a cold start and must not block
    # the server accepting requests.
    async def _backfill_manual_contexts():
        from agent_manager.database import SessionLocal
        from agent_manager.services import manual_context_service

        try:
            # Run the synchronous SQLAlchemy + embed loop in a worker
            # thread so it doesn't starve the event loop.
            def _run():
                db = SessionLocal()
                try:
                    return manual_context_service.backfill_unindexed_contexts(db)
                finally:
                    db.close()

            loop = asyncio.get_running_loop()
            stats = await loop.run_in_executor(None, _run)
            if stats["scanned"] > 0:
                logger.info(
                    "Manual context backfill: scanned=%d indexed=%d skipped=%d failed=%d",
                    stats["scanned"],
                    stats["indexed"],
                    stats["skipped"],
                    stats["failed"],
                )
        except Exception:
            logger.exception("Manual context backfill task crashed")

    backfill_task = asyncio.create_task(_backfill_manual_contexts())

    yield

    # Stop heartbeat + backfill
    heartbeat_task.cancel()
    try:
        await heartbeat_task
    except asyncio.CancelledError:
        pass
    if not backfill_task.done():
        backfill_task.cancel()
        try:
            await backfill_task
        except asyncio.CancelledError:
            pass
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

# Google Slides endpoints
app.include_router(slides_router, prefix="/api/integrations/slides", responses={404: {"description": "Resource not found"}})

# Google Forms endpoints
app.include_router(forms_router, prefix="/api/integrations/forms", responses={404: {"description": "Resource not found"}})

# Google Ads endpoints
app.include_router(ads_router, prefix="/api/integrations/ads", responses={404: {"description": "Resource not found"}})

# YouTube endpoints
app.include_router(youtube_router, prefix="/api/integrations/youtube", responses={404: {"description": "Resource not found"}})

# Google Analytics endpoints
app.include_router(analytics_intg_router, prefix="/api/integrations/analytics", responses={404: {"description": "Resource not found"}})

# Google Search Console endpoints
app.include_router(search_console_router, prefix="/api/integrations/search-console", responses={404: {"description": "Resource not found"}})

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

# Voice call endpoints (outbound calls + Telnyx webhook + media stream WS)
app.include_router(
    voice_call_router,
    prefix="/api/voice",
    responses={404: {"description": "Resource not found"}},
)

# Twitter endpoints
app.include_router(
    twitter_router,
    prefix="/api/integrations/twitter",
    responses={404: {"description": "Resource not found"}},
)

# LinkedIn endpoints
app.include_router(
    linkedin_router,
    prefix="/api/integrations/linkedin",
    responses={404: {"description": "Resource not found"}},
)

# Notion endpoints
app.include_router(
    notion_router,
    prefix="/api/integrations/notion",
    responses={404: {"description": "Resource not found"}},
)

# Slack endpoints
app.include_router(
    slack_router,
    prefix="/api/integrations/slack",
    responses={404: {"description": "Resource not found"}},
)

# GitHub endpoints
app.include_router(
    github_router,
    prefix="/api/integrations/github",
    responses={404: {"description": "Resource not found"}},
)

# Trello endpoints
app.include_router(
    trello_router,
    prefix="/api/integrations/trello",
    responses={404: {"description": "Resource not found"}},
)

# Airtable endpoints
app.include_router(
    airtable_router,
    prefix="/api/integrations/airtable",
    responses={404: {"description": "Resource not found"}},
)

# Asana endpoints
app.include_router(
    asana_router,
    prefix="/api/integrations/asana",
    responses={404: {"description": "Resource not found"}},
)

# ClickUp endpoints
app.include_router(
    clickup_router,
    prefix="/api/integrations/clickup",
    responses={404: {"description": "Resource not found"}},
)

# Todoist endpoints
app.include_router(
    todoist_router,
    prefix="/api/integrations/todoist",
    responses={404: {"description": "Resource not found"}},
)

# Typeform endpoints
app.include_router(
    typeform_router,
    prefix="/api/integrations/typeform",
    responses={404: {"description": "Resource not found"}},
)

# Stripe endpoints
app.include_router(
    stripe_router,
    prefix="/api/integrations/stripe",
    responses={404: {"description": "Resource not found"}},
)

# HubSpot endpoints
app.include_router(
    hubspot_router,
    prefix="/api/integrations/hubspot",
    responses={404: {"description": "Resource not found"}},
)

# Jira endpoints
app.include_router(
    jira_router,
    prefix="/api/integrations/jira",
    responses={404: {"description": "Resource not found"}},
)

# Salesforce endpoints
app.include_router(
    salesforce_router,
    prefix="/api/integrations/salesforce",
    responses={404: {"description": "Resource not found"}},
)

# Monday endpoints
app.include_router(
    monday_router,
    prefix="/api/integrations/monday",
    responses={404: {"description": "Resource not found"}},
)

# Dropbox endpoints
app.include_router(
    dropbox_router,
    prefix="/api/integrations/dropbox",
    responses={404: {"description": "Resource not found"}},
)

# Mailchimp endpoints
app.include_router(
    mailchimp_router,
    prefix="/api/integrations/mailchimp",
    responses={404: {"description": "Resource not found"}},
)

# Calendly endpoints
app.include_router(
    calendly_router,
    prefix="/api/integrations/calendly",
    responses={404: {"description": "Resource not found"}},
)

# Pipedrive endpoints
app.include_router(
    pipedrive_router,
    prefix="/api/integrations/pipedrive",
    responses={404: {"description": "Resource not found"}},
)

# Confluence endpoints
app.include_router(
    confluence_router,
    prefix="/api/integrations/confluence",
    responses={404: {"description": "Resource not found"}},
)

# Zoho CRM endpoints
app.include_router(
    zohocrm_router,
    prefix="/api/integrations/zohocrm",
    responses={404: {"description": "Resource not found"}},
)

# Linear endpoints
app.include_router(
    linear_router,
    prefix="/api/integrations/linear",
    responses={404: {"description": "Resource not found"}},
)

# Box endpoints
app.include_router(
    box_router,
    prefix="/api/integrations/box",
    responses={404: {"description": "Resource not found"}},
)

# Buffer endpoints
app.include_router(
    buffer_router,
    prefix="/api/integrations/buffer",
    responses={404: {"description": "Resource not found"}},
)

# Resend endpoints
app.include_router(
    resend_router,
    prefix="/api/integrations/resend",
    responses={404: {"description": "Resource not found"}},
)

# SendGrid endpoints
app.include_router(
    sendgrid_router,
    prefix="/api/integrations/sendgrid",
    responses={404: {"description": "Resource not found"}},
)

app.include_router(wrike_router, prefix="/api/integrations/wrike", responses={404: {"description": "Resource not found"}})
app.include_router(eventbrite_router, prefix="/api/integrations/eventbrite", responses={404: {"description": "Resource not found"}})
app.include_router(basecamp_router, prefix="/api/integrations/basecamp", responses={404: {"description": "Resource not found"}})
app.include_router(chargebee_router, prefix="/api/integrations/chargebee", responses={404: {"description": "Resource not found"}})
app.include_router(clockify_router, prefix="/api/integrations/clockify", responses={404: {"description": "Resource not found"}})
app.include_router(quickbooks_router, prefix="/api/integrations/quickbooks", responses={404: {"description": "Resource not found"}})
app.include_router(xero_router, prefix="/api/integrations/xero", responses={404: {"description": "Resource not found"}})
app.include_router(twilio_router, prefix="/api/integrations/twilio", responses={404: {"description": "Resource not found"}})
app.include_router(whatsapp_router, prefix="/api/integrations/whatsapp", responses={404: {"description": "Resource not found"}})
app.include_router(telegram_router, prefix="/api/integrations/telegram", responses={404: {"description": "Resource not found"}})
app.include_router(wordpress_router, prefix="/api/integrations/wordpress", responses={404: {"description": "Resource not found"}})
app.include_router(woocommerce_router, prefix="/api/integrations/woocommerce", responses={404: {"description": "Resource not found"}})
app.include_router(square_router, prefix="/api/integrations/square", responses={404: {"description": "Resource not found"}})
app.include_router(sentry_router, prefix="/api/integrations/sentry", responses={404: {"description": "Resource not found"}})
app.include_router(posthog_router, prefix="/api/integrations/posthog", responses={404: {"description": "Resource not found"}})
app.include_router(outlook_router, prefix="/api/integrations/outlook", responses={404: {"description": "Resource not found"}})
app.include_router(microsoft_teams_router, prefix="/api/integrations/microsoft-teams", responses={404: {"description": "Resource not found"}})
app.include_router(onedrive_router, prefix="/api/integrations/onedrive", responses={404: {"description": "Resource not found"}})

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

# Billing endpoints: /api/billing
app.include_router(
    billing_router,
    prefix="/api",
    responses={404: {"description": "Resource not found"}},
)

# Agent Activity endpoints: /api/agents/{agent_id}/activity
app.include_router(
    agent_activity_router,
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


@app.websocket("/api/activity/ws")
async def activity_websocket(ws: WebSocket):
    """Real-time agent activity stream."""
    await activity_ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        activity_ws_manager.disconnect(ws)

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
