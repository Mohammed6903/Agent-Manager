"""Agent CRUD operations — filesystem + OpenClaw Gateway registration."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .config import settings
from .openclaw import run_openclaw
from .schemas import AgentResponse, CreateAgentRequest, UpdateAgentRequest

logger = logging.getLogger("agent_manager.agent_service")


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _workspace(agent_id: str) -> Path:
    return Path(settings.OPENCLAW_STATE_DIR) / f"workspace-{agent_id}"


def _agent_dir(agent_id: str) -> Path:
    return Path(settings.OPENCLAW_STATE_DIR) / "agents" / agent_id / "agent"


def _default_identity(agent_id: str, name: str, role: str) -> str:
    return (
        f"# Identity\n"
        f"Name: {name}\n"
        f"Agent ID: {agent_id}\n"
        f"Role: {role}\n"
    )


def _default_soul(agent_id: str, name: str, role: str) -> str:
    return (
        f"# {name}\n"
        f"You are {name}. You are a helpful AI assistant whose role is: {role}.\n"
        f"Be concise, accurate, and professional.\n"
        f"Your agent ID is {agent_id}. Always use it exactly when calling tools.\n"
    )


async def _get_existing_agents() -> list[dict[str, Any]]:
    """Return the list of currently registered agents from the gateway config."""
    try:
        data = await run_openclaw(["agents", "list", "--json"])
        # The response can be a list directly or wrapped under a key.
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # Try common shapes: {agents: [...]}, {list: [...]}, {payload: [...]}
            for key in ("agents", "list", "payload", "data"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            # If the dict itself looks like a single agent entry, wrap it.
            if "id" in data:
                return [data]
        return []
    except HTTPException as exc:
        # If the CLI errors (e.g. no agents registered yet), return empty list.
        logger.warning("Failed to list agents (returning empty): %s", exc.detail)
        return []


async def _get_config_hash() -> str:
    """Fetch the current gateway config hash (top-level `.hash` key)."""
    data = await run_openclaw(["gateway", "call", "config.get", "--params", "{}", "--json"])
    config_hash = data.get("hash")
    if not config_hash:
        raise HTTPException(
            status_code=500,
            detail=f"Could not extract config hash from config.get response: {json.dumps(data)[:300]}",
        )
    return config_hash


def _build_agents_raw(agents: list[dict[str, Any]]) -> str:
    """Build the HOCON-style ``raw`` string for ``config.patch``.

    The raw value must include ALL agents (existing + new) because
    ``config.patch`` replaces the list rather than merging.
    """
    entries: list[str] = []
    for a in agents:
        entry = (
            f'{{ id: \\"{a["id"]}\\", '
            f'name: \\"{a["name"]}\\", '
            f'workspace: \\"{a["workspace"]}\\", '
            f'agentDir: \\"{a["agentDir"]}\\" }}'
        )
        entries.append(entry)
    joined = ", ".join(entries)
    return f"{{ agents: {{ list: [{joined}] }} }}"


# ── Public API ──────────────────────────────────────────────────────────────────


async def create_agent(req: CreateAgentRequest) -> AgentResponse:
    """Create a new agent: filesystem → gateway registration."""
    agent_id = req.agent_id

    # 1. Check for duplicates
    existing = await _get_existing_agents()
    if any(a.get("id") == agent_id for a in existing):
        raise HTTPException(status_code=409, detail=f"Agent '{agent_id}' already exists")

    workspace = _workspace(agent_id)
    agent_dir = _agent_dir(agent_id)

    # 2. Create filesystem
    await asyncio.to_thread(os.makedirs, str(workspace), exist_ok=True)
    await asyncio.to_thread(os.makedirs, str(agent_dir), exist_ok=True)

    # 3. Write IDENTITY.md
    identity_content = req.identity or _default_identity(agent_id, req.name, req.role)
    await asyncio.to_thread(workspace.joinpath("IDENTITY.md").write_text, identity_content)

    # 4. Write SOUL.md
    soul_content = req.soul or _default_soul(agent_id, req.name, req.role)
    await asyncio.to_thread(workspace.joinpath("SOUL.md").write_text, soul_content)

    # 5. Get fresh config hash
    config_hash = await _get_config_hash()

    # 6. Build full agent list (existing + new)
    new_entry = {
        "id": agent_id,
        "name": req.name,
        "workspace": str(workspace),
        "agentDir": str(agent_dir),
    }
    all_agents = existing + [new_entry]
    raw = _build_agents_raw(all_agents)

    # 7. Patch config
    params = json.dumps({"baseHash": config_hash, "raw": raw})
    result = await run_openclaw(["gateway", "call", "config.patch", "--params", params, "--json"])

    if not result.get("ok"):
        logger.error("config.patch did not return ok=true: %s", result)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "config_patch_failed",
                "message": "Gateway config.patch did not return ok=true",
                "gateway_response": result,
            },
        )

    logger.info("Agent '%s' created successfully", agent_id)
    return AgentResponse(
        agent_id=agent_id,
        name=req.name,
        workspace=str(workspace),
        agent_dir=str(agent_dir),
        status="created",
    )


async def list_agents() -> list[dict[str, Any]]:
    """Return all registered agents."""
    return await _get_existing_agents()


async def get_agent(agent_id: str) -> dict[str, Any]:
    """Return a single agent by ID or raise 404."""
    agents = await _get_existing_agents()
    for a in agents:
        if a.get("id") == agent_id:
            return a
    raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")


async def update_agent(agent_id: str, req: UpdateAgentRequest) -> AgentResponse:
    """Update an agent's identity / soul files."""
    # Ensure agent exists
    agent = await get_agent(agent_id)
    workspace = _workspace(agent_id)

    if not workspace.exists():
        raise HTTPException(status_code=404, detail=f"Workspace for '{agent_id}' not found on disk")

    # Update SOUL.md if provided
    if req.soul is not None:
        await asyncio.to_thread(workspace.joinpath("SOUL.md").write_text, req.soul)

    # Update IDENTITY.md
    if req.identity is not None:
        await asyncio.to_thread(workspace.joinpath("IDENTITY.md").write_text, req.identity)
    elif req.name is not None or req.role is not None:
        # Re-generate IDENTITY.md with updated fields
        identity_path = workspace / "IDENTITY.md"
        current_name = agent.get("name", "")
        current_role = ""

        # Try to read current role from IDENTITY.md
        if identity_path.exists():
            content = await asyncio.to_thread(identity_path.read_text)
            for line in content.splitlines():
                if line.startswith("Role:"):
                    current_role = line.split(":", 1)[1].strip()

        new_name = req.name if req.name is not None else current_name
        new_role = req.role if req.role is not None else current_role
        identity_content = _default_identity(agent_id, new_name, new_role)
        await asyncio.to_thread(identity_path.write_text, identity_content)

    # If name changed, we should also update the gateway config
    if req.name is not None:
        config_hash = await _get_config_hash()
        existing = await _get_existing_agents()
        for a in existing:
            if a.get("id") == agent_id:
                a["name"] = req.name
                break
        raw = _build_agents_raw(existing)
        params = json.dumps({"baseHash": config_hash, "raw": raw})
        await run_openclaw(["gateway", "call", "config.patch", "--params", params, "--json"])

    return AgentResponse(
        agent_id=agent_id,
        name=req.name or agent.get("name", ""),
        workspace=str(workspace),
        agent_dir=str(_agent_dir(agent_id)),
        status="updated",
    )


async def delete_agent(agent_id: str) -> dict[str, str]:
    """Delete an agent: gateway de-registration + filesystem cleanup."""
    # 1. Remove from gateway config
    try:
        await run_openclaw(["agents", "delete", agent_id, "--force", "--json"])
    except HTTPException as exc:
        logger.warning("openclaw agents delete failed (may already be removed): %s", exc.detail)

    # 2. Clean up filesystem
    workspace = _workspace(agent_id)
    agent_base = Path(settings.OPENCLAW_STATE_DIR) / "agents" / agent_id

    for path in (workspace, agent_base):
        if path.exists():
            await asyncio.to_thread(shutil.rmtree, str(path))

    logger.info("Agent '%s' deleted", agent_id)
    return {"status": "deleted", "agent_id": agent_id}
