"""Server-side heartbeat — broadcasts every 5 seconds, persists every 30 seconds.

The WebSocket broadcast runs every 5s so the frontend feels live.
The DB write only happens every 30s to keep storage sane (~2,880 rows/agent/day
instead of 17,280).

Launched as a background asyncio task during app lifespan.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import psutil
from sqlalchemy import select

from ..database import SessionLocal
from ..models.agent_subscription import AgentSubscription
from ..repositories.agent_activity_repository import AgentActivityRepository
from ..ws_manager import activity_ws_manager

logger = logging.getLogger("agent_manager.services.heartbeat_service")

_SERVER_BOOT_TIME = time.time()
BROADCAST_INTERVAL = 5   # seconds — WebSocket push (live feel)
PERSIST_INTERVAL = 30    # seconds — DB write (storage-friendly)


async def _run_heartbeat_loop():
    """Infinite loop that emits heartbeats for every active agent."""
    logger.info(
        "Heartbeat service started (broadcast=%ds, persist=%ds)",
        BROADCAST_INTERVAL, PERSIST_INTERVAL,
    )

    tick = 0
    while True:
        try:
            should_persist = (tick % (PERSIST_INTERVAL // BROADCAST_INTERVAL)) == 0
            await _emit_heartbeats(persist=should_persist)
        except Exception:
            logger.exception("Heartbeat cycle failed")

        tick += 1
        await asyncio.sleep(BROADCAST_INTERVAL)


async def _emit_heartbeats(*, persist: bool):
    """Single heartbeat cycle — always broadcast, optionally persist."""
    db = SessionLocal() if persist else None
    try:
        now = time.time()
        uptime_secs = int(now - _SERVER_BOOT_TIME)
        timestamp = datetime.now(timezone.utc).isoformat()

        # System metrics (once per cycle)
        cpu_percent = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        mem_used_mb = round(mem.used / (1024 * 1024))
        mem_percent = mem.percent

        # Get all subscriptions
        session = db or SessionLocal()
        try:
            subs = session.execute(select(AgentSubscription)).scalars().all()
        finally:
            if not db:
                session.close()

        if not subs:
            return

        repo = AgentActivityRepository(db) if db else None

        for sub in subs:
            agent_id = sub.agent_id
            status = "offline" if sub.status in ("locked", "deleted") else "online"
            summary = f"Heartbeat {status.upper()} — cpu {cpu_percent}% mem {mem_used_mb}MB ({mem_percent}%)"

            metadata = {
                "cpu_percent": cpu_percent,
                "mem_used_mb": mem_used_mb,
                "mem_percent": mem_percent,
                "uptime_seconds": uptime_secs,
            }

            # Persist to DB only on persist ticks
            activity_id = None
            if repo:
                try:
                    activity = repo.create(
                        agent_id=agent_id,
                        activity_type="heartbeat",
                        summary=summary,
                        metadata=metadata,
                        status=status,
                    )
                    activity_id = str(activity.id)
                except Exception:
                    logger.exception("Failed to persist heartbeat for %s", agent_id)

            # Always broadcast via WebSocket
            event_data = {
                "id": activity_id or f"hb-{agent_id}-{int(now)}",
                "agent_id": agent_id,
                "activity_type": "heartbeat",
                "summary": summary,
                "metadata": metadata,
                "status": status,
                "created_at": timestamp,
            }
            await activity_ws_manager.broadcast("agent_activity", event_data)

    finally:
        if db:
            db.close()


def start_heartbeat_task() -> asyncio.Task:
    """Launch the heartbeat loop as a background asyncio task."""
    return asyncio.create_task(_run_heartbeat_loop())
