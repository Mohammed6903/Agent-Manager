"""Fire-and-forget cache invalidation notifications to the agent-manager
OpenClaw plugin.

When the backend mutates an agent's integration assignments, this helper
asks the plugin running inside the openclaw gateway to refresh its
in-process per-agent integration cache. The plugin's tool factories then
see the new state on the very next model attempt instead of waiting for
the cache TTL.

The notification is best-effort: failures are logged at DEBUG and never
raise. The plugin's 5-second stale-while-revalidate TTL is the safety
net for missed pushes.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

import httpx

from ..config import settings

logger = logging.getLogger("agent_manager.clients.plugin_notifier")

_REFRESH_TIMEOUT_S = 2.0


def _gateway_http_base() -> str:
    """Return the gateway's HTTP base URL.

    Settings store the gateway as a ws:// URL by convention; the openclaw
    gateway exposes its HTTP server on the same host:port, so we just
    swap the scheme.
    """
    url = settings.OPENCLAW_GATEWAY_URL or "http://localhost:18789"
    return (
        url.replace("ws://", "http://", 1)
        .replace("wss://", "https://", 1)
        .rstrip("/")
    )


def _post_refresh(agent_id: str) -> None:
    """Synchronous POST to the plugin invalidation endpoint. Never raises."""
    url = f"{_gateway_http_base()}/agent-manager/refresh-integrations/{agent_id}"
    try:
        with httpx.Client(timeout=_REFRESH_TIMEOUT_S) as client:
            r = client.post(url)
        if r.status_code >= 300:
            logger.debug(
                "plugin refresh non-2xx for %s: %s %s", agent_id, r.status_code, r.text[:200]
            )
    except Exception as exc:
        # Plugin may be down, gateway restarting, etc. The TTL safety net
        # in the plugin will pick up the change within ~5 seconds.
        logger.debug("plugin refresh failed for %s: %s", agent_id, exc)


def notify_plugin_integration_change(agent_id: Optional[str]) -> None:
    """Fire-and-forget plugin cache invalidation for a single agent.

    Schedules the HTTP POST on a daemon thread so the calling code (a
    repository commit, an OAuth callback, etc.) returns immediately.
    Safe to call from any context (sync or async). Never raises.
    """
    if not agent_id:
        return
    try:
        threading.Thread(
            target=_post_refresh,
            args=(agent_id,),
            daemon=True,
            name=f"plugin-notify-{agent_id[:12]}",
        ).start()
    except Exception as exc:
        logger.debug("could not spawn plugin notify thread for %s: %s", agent_id, exc)
