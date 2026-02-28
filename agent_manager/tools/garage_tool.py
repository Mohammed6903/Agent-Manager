"""Garage community feed tool — lets agents post on the Garage feed."""
from __future__ import annotations

import json
import logging
import httpx

from ..config import settings

logger = logging.getLogger("agent_manager.tools.garage_tool")


GARAGE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_garage_post",
            "description": (
                "Post a message to the Garage community feed. "
                "Use this when the user asks you to post, share, or publish something on the feed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The text content of the post to publish on the Garage feed.",
                    }
                },
                "required": ["content"],
            },
        },
    }
]


async def load_garage_credentials(agent_id: str) -> dict | None:
    """Fetch Garage Feed credentials from GmailService secrets store.

    Returns the secret_data dict, or None if not connected / unreachable.
    """
    if not settings.GMAIL_SERVICE_URL:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.GMAIL_SERVICE_URL}/secrets/{agent_id}/garage_feed"
            )
            if resp.status_code == 200:
                return resp.json().get("secret_data")
    except Exception as exc:
        logger.warning("Could not load Garage credentials for agent %s: %s", agent_id, exc)
    return None


async def execute_create_garage_post(agent_id: str, content: str) -> str:
    """Execute the create_garage_post tool via the agent-manager's /api/garage/posts endpoint."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.SERVER_URL}/api/garage/posts",
                json={"agent_id": agent_id, "content": content},
            )
            if resp.status_code in (200, 201):
                return "Post published successfully on the Garage feed!"
            return f"Failed to post: HTTP {resp.status_code} — {resp.text[:300]}"
    except Exception as exc:
        logger.error("Garage post error for agent %s: %s", agent_id, exc)
        return f"Error connecting to Garage: {exc}"
