"""WebSocket connection manager for broadcasting real-time task events."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("agent_manager.ws_manager")


class ConnectionManager:
    """Tracks active WebSocket connections and broadcasts events."""

    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)
        logger.info("WS client connected (%d total)", len(self._connections))

    def disconnect(self, ws: WebSocket):
        self._connections.remove(ws)
        logger.info("WS client disconnected (%d total)", len(self._connections))

    async def broadcast(self, event_type: str, data: Any):
        """Send a JSON event to every connected client."""
        message = json.dumps({"event": event_type, "data": data}, default=str)
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)


# Singleton used across the app
task_ws_manager = ConnectionManager()
cron_ws_manager = ConnectionManager()
