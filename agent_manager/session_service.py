"""Session inspection and management."""
from __future__ import annotations
import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException
from .config import settings

logger = logging.getLogger("agent_manager.session_service")


def _sessions_index(agent_id: str) -> dict:
    """Read sessions.json for a specific agent."""
    sessions_file = (
        Path(settings.OPENCLAW_STATE_DIR)
        / "agents"
        / agent_id
        / "sessions"
        / "sessions.json"
    )
    if not sessions_file.exists():
        return {}
    return json.loads(sessions_file.read_text())


async def list_sessions(agent_id: str, user_id: Optional[str] = None) -> Any:
    """
    List sessions for a specific agent.
    If user_id is provided, returns only that user's sessions.
    """
    index = await asyncio.to_thread(_sessions_index, agent_id)

    sessions = []
    for session_key, meta in index.items():
        # Filter by user_id if provided
        if user_id:
            # Session key format: agent:{agent_id}:openai-user:{agent_id}:{user_id}
            # or agent:{agent_id}:openai-user:{agent_id}:{user_id}:{session_id}
            if f"openai-user:{agent_id}:{user_id}" not in session_key:
                continue

        sessions.append({
            "session_key": session_key,
            "agent_id": agent_id,
            "session_id": meta.get("sessionId"),
            "updated_at": meta.get("updatedAt"),
            "input_tokens": meta.get("inputTokens", 0),
            "output_tokens": meta.get("outputTokens", 0),
            "total_tokens": meta.get("totalTokens", 0),
            "model": meta.get("model"),
            "aborted": meta.get("abortedLastRun", False),
        })

    # Sort by most recent first
    sessions.sort(key=lambda x: x["updated_at"] or 0, reverse=True)

    return {
        "agent_id": agent_id,
        "user_id": user_id,
        "sessions": sessions,
        "count": len(sessions),
    }


async def list_all_sessions(user_id: Optional[str] = None) -> Any:
    """
    List all sessions across all agents.
    If user_id is provided, returns only that user's sessions.
    """
    agents_dir = Path(settings.OPENCLAW_STATE_DIR) / "agents"

    if not agents_dir.exists():
        return {"sessions": [], "count": 0}

    all_sessions = []

    for agent_dir in agents_dir.iterdir():
        if not agent_dir.is_dir():
            continue
        agent_id = agent_dir.name
        result = await list_sessions(agent_id, user_id=user_id)
        all_sessions.extend(result["sessions"])

    # Sort all by most recent first
    all_sessions.sort(key=lambda x: x["updated_at"] or 0, reverse=True)

    return {
        "user_id": user_id,
        "sessions": all_sessions,
        "count": len(all_sessions),
    }


async def get_session_history(
    agent_id: str,
    user_id: str,
    session_id: Optional[str] = None,
    limit: int = 50,
) -> Any:
    """
    Get chat history for a specific user+agent session.
    Reads JSONL transcript directly — filters to user/assistant text only.
    """
    index = await asyncio.to_thread(_sessions_index, agent_id)

    # Build session key — must match what chat endpoint sends
    if session_id:
        session_key = f"agent:{agent_id}:openai-user:{agent_id}:{user_id}:{session_id}"
    else:
        session_key = f"agent:{agent_id}:openai-user:{agent_id}:{user_id}"

    session_meta = index.get(session_key)
    if not session_meta:
        return {
            "agent_id": agent_id,
            "user_id": user_id,
            "session_key": session_key,
            "messages": [],
            "count": 0,
        }

    transcript_id = session_meta.get("sessionId")
    transcript_file = (
        Path(settings.OPENCLAW_STATE_DIR)
        / "agents"
        / agent_id
        / "sessions"
        / f"{transcript_id}.jsonl"
    )

    if not transcript_file.exists():
        return {
            "agent_id": agent_id,
            "user_id": user_id,
            "session_key": session_key,
            "messages": [],
            "count": 0,
        }

    def _read_transcript():
        lines = transcript_file.read_text().strip().splitlines()
        return lines[-limit:]  # last N lines

    raw_lines = await asyncio.to_thread(_read_transcript)

    messages = []
    for line in raw_lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        role = entry.get("message", {}).get("role")
        if role not in ("user", "assistant"):
            continue

        # Extract text content only — skip tool calls and tool results
        content = ""
        raw_content = entry.get("message", {}).get("content", [])

        if isinstance(raw_content, str):
            content = raw_content
        elif isinstance(raw_content, list):
            for block in raw_content:
                if isinstance(block, str):
                    content = block
                    break
                if isinstance(block, dict) and block.get("type") == "text":
                    content = block.get("text", "")
                    break

        if content:
            messages.append({
                "role": role,
                "content": content,
                "timestamp": entry.get("timestamp"),
            })

    return {
        "agent_id": agent_id,
        "user_id": user_id,
        "session_key": session_key,
        "messages": messages,
        "count": len(messages),
    }


async def clear_agent_memory(agent_id: str) -> dict[str, str]:
    """Clear persistent memory (MEMORY.md) for an agent."""
    memory_path = (
        Path(settings.OPENCLAW_STATE_DIR)
        / f"workspace-{agent_id}"
        / "MEMORY.md"
    )

    if not memory_path.parent.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "error": "workspace_not_found",
                "message": f"Workspace for agent '{agent_id}' not found",
                "expected_path": str(memory_path.parent),
            },
        )

    await asyncio.to_thread(memory_path.write_text, "")
    logger.info("Cleared MEMORY.md for agent '%s'", agent_id)
    return {"status": "cleared", "agent_id": agent_id}