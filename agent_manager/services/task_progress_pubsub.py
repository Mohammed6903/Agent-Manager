"""Bridge Celery task progress to FastAPI's task_ws_manager via Redis pub/sub.

Celery workers run in separate processes from the FastAPI app, so they
can't call task_ws_manager.broadcast() directly. They publish progress
JSON to a Redis pub/sub channel; the FastAPI app spins up one async
subscriber on startup that re-broadcasts every message through the
existing in-process WS manager. Roam-backend's openclawWs.ts bridge
forwards `task_progress` events to clients whose accessible_agent_ids
include data.agent_id.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import redis as redis_lib
import redis.asyncio as redis_async

from agent_manager.config import settings
from agent_manager.ws_manager import task_ws_manager

logger = logging.getLogger(__name__)

CHANNEL = "openclaw:task_progress"
EVENT_NAME = "task_progress"


def _sync_redis() -> redis_lib.Redis:
    """Synchronous Redis client for use from Celery workers."""
    return redis_lib.from_url(settings.REDIS_URL, decode_responses=True)


def _async_redis() -> redis_async.Redis:
    """Async Redis client for use from the FastAPI subscriber."""
    return redis_async.from_url(settings.REDIS_URL, decode_responses=False)


def publish_task_progress(payload: dict[str, Any]) -> None:
    """Publish progress payload to the channel. Safe to call from Celery workers.

    Payload MUST include `task_id` and `agent_id` for the bridge's RBAC
    filter to forward it to the right downstream clients.
    """
    if "task_id" not in payload or "agent_id" not in payload:
        logger.warning(
            "publish_task_progress called without task_id+agent_id (got keys: %s) — bridge will drop",
            list(payload.keys()),
        )
    try:
        msg = json.dumps(payload, default=str)
        _sync_redis().publish(CHANNEL, msg)
    except Exception:
        logger.exception("Failed to publish task progress")


def _decode_message(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not isinstance(raw, str):
        return None
    try:
        decoded = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return None
    return decoded if isinstance(decoded, dict) else None


async def subscribe_and_broadcast(stop_event: asyncio.Event) -> None:
    """Long-running task: subscribe to the channel and broadcast each message
    via task_ws_manager. Reconnects with backoff on Redis errors.
    """
    backoff = 1.0
    while not stop_event.is_set():
        try:
            client = _async_redis()
            pubsub = client.pubsub()
            await pubsub.subscribe(CHANNEL)
            logger.info("task_progress subscriber connected to %s", CHANNEL)
            backoff = 1.0
            try:
                async for message in pubsub.listen():
                    if stop_event.is_set():
                        break
                    if message.get("type") != "message":
                        continue
                    payload = _decode_message(message.get("data"))
                    if payload is None:
                        continue
                    try:
                        await task_ws_manager.broadcast(EVENT_NAME, payload)
                    except Exception:
                        logger.exception("task_ws_manager.broadcast failed")
            finally:
                try:
                    await pubsub.unsubscribe(CHANNEL)
                    await pubsub.close()
                    await client.close()
                except Exception:
                    pass
        except Exception:
            logger.exception("task_progress subscriber crashed — reconnecting in %.1fs", backoff)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=backoff)
                return
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, 30.0)
