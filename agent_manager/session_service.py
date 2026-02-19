"""Session inspection and management."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .config import settings
from .openclaw import run_openclaw

logger = logging.getLogger("agent_manager.session_service")


async def list_sessions(agent_id: str) -> Any:
    """List sessions for a specific agent."""
    return await run_openclaw(["sessions", "--agent", agent_id, "--json"])


async def list_all_sessions() -> Any:
    """List all sessions across all agents."""
    return await run_openclaw(["sessions", "--json"])


async def clear_agent_memory(agent_id: str) -> dict[str, str]:
    """Clear persistent memory (MEMORY.md) for an agent.

    This effectively resets the agent's long-term memory.
    A new ``user`` field value should also be used in subsequent chat
    requests for a fully clean session.
    """
    memory_path = Path(settings.OPENCLAW_STATE_DIR) / f"workspace-{agent_id}" / "MEMORY.md"

    if not memory_path.parent.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "error": "workspace_not_found",
                "message": f"Workspace for agent '{agent_id}' not found on disk",
                "expected_path": str(memory_path.parent),
                "hint": "The agent may not exist or its filesystem was not created",
            },
        )

    await asyncio.to_thread(memory_path.write_text, "")
    logger.info("Cleared MEMORY.md for agent '%s'", agent_id)
    return {"status": "cleared", "agent_id": agent_id}
