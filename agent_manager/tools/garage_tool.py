"""Garage community feed tool — lets agents post on the Garage feed."""
from __future__ import annotations

import json
import logging

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..services.secret_service import SecretService

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


def load_garage_credentials(db: Session, agent_id: str) -> dict | None:
    """Fetch Garage Feed credentials from the local secret store.

    Returns the decrypted secret_data dict, or None if not found.
    """
    return SecretService.get_secret(db, agent_id, "garage_feed")


async def execute_create_garage_post(db: Session, agent_id: str, content: str) -> str:
    """Execute the create_garage_post tool. Returns a human-readable result string."""
    creds = load_garage_credentials(db, agent_id)
    if not creds:
        return "Error: Garage Feed skill is not connected for this agent."

    token = creds.get("token", "")
    org_id = creds.get("orgId", "")
    channel_ids = creds.get("channelIds", [])

    # channelIds may come back as a string from decryption — parse if needed
    if isinstance(channel_ids, str):
        try:
            channel_ids = json.loads(channel_ids)
        except (ValueError, TypeError):
            channel_ids = [channel_ids] if channel_ids else []

    if not token or not org_id:
        return "Error: Garage Feed credentials are incomplete. Please reconnect the skill."

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.GARAGE_API_URL}/feed/posts",
                params={"orgId": org_id},
                json={"content": content, "channelIds": channel_ids},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code in (200, 201):
                return "Post published successfully on the Garage feed!"
            return f"Failed to post: HTTP {resp.status_code} — {resp.text[:300]}"
    except Exception as exc:
        logger.error("Garage post error for agent %s: %s", agent_id, exc)
        return f"Error connecting to Garage: {exc}"
