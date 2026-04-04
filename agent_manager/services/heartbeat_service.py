"""Server-side heartbeat — runs every 5 seconds for all active agents.

Persists heartbeat to agent_activities and broadcasts via WebSocket.
Launched as a background asyncio task during app lifespan.
"""

from __future__ import annotations

import asyncio
import logging
import time

import psutil
from sqlalchemy import select

from ..database import SessionLocal
from ..models.agent_subscription import AgentSubscription
from ..repositories.agent_activity_repository import AgentActivityRepository
from ..ws_manager import activity_ws_manager

logger = logging.getLogger("agent_manager.services.heartbeat_service")

_SERVER_BOOT_TIME = time.time()
HEARTBEAT_INTERVAL = 5  # seconds


async def _run_heartbeat_loop():
    """Infinite loop that emits heartbeats for every active agent."""
    logger.info("Heartbeat service started (interval=%ds)", HEARTBEAT_INTERVAL)

    while True:
        try:
            await _emit_heartbeats()
        except Exception:
            logger.exception("Heartbeat cycle failed")

        await asyncio.sleep(HEARTBEAT_INTERVAL)


async def _emit_heartbeats():
    """Single heartbeat cycle — query agents, log + broadcast for each."""
    db = SessionLocal()
    try:
        now = time.time()
        uptime_secs = int(now - _SERVER_BOOT_TIME)

        # System metrics (once per cycle, shared across all agents)
        cpu_percent = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        mem_used_mb = round(mem.used / (1024 * 1024))
        mem_percent = mem.percent

        # Get all subscriptions to determine which agents exist + their status
        subs = db.execute(select(AgentSubscription)).scalars().all()

        if not subs:
            return

        repo = AgentActivityRepository(db)

        for sub in subs:
            agent_id = sub.agent_id
            status = "offline" if sub.status in ("locked", "deleted") else "online"

            summary = f"Heartbeat {status.upper()} — cpu {cpu_percent}% mem {mem_used_mb}MB ({mem_percent}%)"

            activity = repo.create(
                agent_id=agent_id,
                activity_type="heartbeat",
                summary=summary,
                metadata={
                    "cpu_percent": cpu_percent,
                    "mem_used_mb": mem_used_mb,
                    "mem_percent": mem_percent,
                    "uptime_seconds": uptime_secs,
                },
                status=status,
            )

            # Broadcast via WebSocket
            event_data = {
                "id": str(activity.id),
                "agent_id": agent_id,
                "activity_type": "heartbeat",
                "summary": summary,
                "metadata": {
                    "cpu_percent": cpu_percent,
                    "mem_used_mb": mem_used_mb,
                    "mem_percent": mem_percent,
                    "uptime_seconds": uptime_secs,
                },
                "status": status,
                "created_at": activity.created_at.isoformat(),
            }
            await activity_ws_manager.broadcast("agent_activity", event_data)

    finally:
        db.close()


def start_heartbeat_task() -> asyncio.Task:
    """Launch the heartbeat loop as a background asyncio task."""
    return asyncio.create_task(_run_heartbeat_loop())
