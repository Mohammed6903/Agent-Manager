"""Garage tools — feed posting and proactive chat message delivery."""
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
    },
    {
        "type": "function",
        "function": {
            "name": "deliver_chat_message",
            "description": (
                "Send a message to the user's chat UI. Use this after completing a cron/scheduled job "
                "to deliver the summary, or anytime you need to proactively send a message outside of "
                "a direct conversation. Write the content as a clean, human-readable message — "
                "not raw JSON or code blocks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The message content to deliver to the user's chat.",
                    },
                },
                "required": ["content"],
            },
        },
    },
]


async def send_cron_summary_to_chat(
    user_id: str,
    session_id: str,
    agent_id: str,
    summary: str,
) -> dict:
    """Send a cron-run summary to the Garage chat via POST /api/chat/message."""
    url = f"{settings.GARAGE_CHAT_INTERNAL_URL.rstrip('/')}/internal/chat/message"
    body = {
        "userId": user_id,
        "sessionId": session_id,
        "agentId": agent_id,
        "message": summary,
        "type": "system",
        "source": "cron-webhook",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {settings.GARAGE_INTERNAL_API_KEY}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                logger.info("Cron summary delivered to chat: messageId=%s", data.get("messageId"))
                return data
            logger.error("Chat delivery failed: HTTP %s — %s", resp.status_code, resp.text[:300])
            return {"ok": False, "error": f"HTTP {resp.status_code}"}
    except Exception as exc:
        logger.error("Error sending cron summary to chat: %s", exc)
        return {"ok": False, "error": str(exc)}


async def execute_deliver_chat_message(
    agent_id: str, user_id: str, session_id: str, content: str
) -> str:
    """Execute the deliver_chat_message tool — sends a message to the user's chat UI."""
    url = f"{settings.GARAGE_CHAT_INTERNAL_URL.rstrip('/')}/internal/chat/message"
    body = {
        "userId": user_id,
        "sessionId": session_id,
        "agentId": agent_id,
        "message": content,
        "type": "system",
        "source": "agent-tool",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {settings.GARAGE_INTERNAL_API_KEY}"},
            )
            if resp.status_code == 200:
                logger.info("Chat message delivered for agent %s to user %s", agent_id, user_id)
                return "Message delivered successfully."
            logger.error("Chat delivery failed: HTTP %s — %s", resp.status_code, resp.text[:300])
            return f"Failed to deliver message: HTTP {resp.status_code}"
    except Exception as exc:
        logger.error("Error delivering chat message for agent %s: %s", agent_id, exc)
        return f"Error delivering message: {exc}"


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
