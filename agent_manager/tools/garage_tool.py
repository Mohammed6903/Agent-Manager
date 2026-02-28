"""Garage community feed tool — lets agents post on the Garage feed."""
from __future__ import annotations

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
                    },
                    "channelIds": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional channel ID(s) to post to. Use when the user specifies a channel ID.",
                    },
                },
                "required": ["content"],
            },
        },
    }
]


async def execute_create_garage_post(
    agent_id: str, content: str, channel_ids: list[str] | None = None
) -> str:
    """Execute the create_garage_post tool via the agent-manager's /api/garage/posts endpoint."""
    body: dict = {"agent_id": agent_id, "content": content}
    if channel_ids:
        body["channelIds"] = channel_ids
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.SERVER_URL}/api/garage/posts",
                json=body,
            )
            if resp.status_code in (200, 201):
                return "Post published successfully on the Garage feed!"
            return f"Failed to post: HTTP {resp.status_code} — {resp.text[:300]}"
    except Exception as exc:
        logger.error("Garage post error for agent %s: %s", agent_id, exc)
        return f"Error connecting to Garage: {exc}"
