from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, List

from fastapi import HTTPException

from ..config import settings
from ..schemas import AgentResponse, CreateAgentRequest, UpdateAgentRequest
from ..repositories.storage import StorageRepository
from ..clients.gateway_client import GatewayClient

logger = logging.getLogger("agent_manager.services.agent_service")

class AgentService:
    def __init__(self, storage: StorageRepository, gateway: GatewayClient):
        self.storage = storage
        self.gateway = gateway

    def _workspace(self, agent_id: str) -> str:
        return str(Path(settings.OPENCLAW_STATE_DIR) / f"workspace-{agent_id}")

    def _agent_dir(self, agent_id: str) -> str:
        return str(Path(settings.OPENCLAW_STATE_DIR) / "agents" / agent_id / "agent")

    def _default_identity(self, agent_id: str, name: str, role: str) -> str:
        return (
            "# Identity" +
            f"Name: {name}"
            f"Agent ID: {agent_id}"
            f"Role: {role}"
        )

    def _default_soul(self, agent_id: str, name: str, role: str) -> str:
        return (
            f"# {name}"
            f"You are {name}. You are a helpful AI assistant whose role is: {role}."
            f"Be concise, accurate, and professional."
            f"Your agent ID is {agent_id}. Always use it exactly when calling tools."
        )

    def _build_agents_raw(self, agents: List[dict[str, Any]]) -> str:
        entries: List[str] = []
        for a in agents:
            entry = (
                f'{{ id: "{a["id"]}", '
                f'name: "{a["name"]}", '
                f'workspace: "{a["workspace"]}", '
                f'agentDir: "{a["agentDir"]}" }}'
            )
            entries.append(entry)
        joined = ", ".join(entries)
        return f"{{ agents: {{ list: [{joined}] }} }}"

    async def create_agent(self, req: CreateAgentRequest) -> AgentResponse:
        agent_id = req.agent_id

        existing = await self.gateway.list_agents()
        if any(a.get("id") == agent_id for a in existing):
            raise HTTPException(status_code=409, detail=f"Agent '{agent_id}' already exists")

        workspace = self._workspace(agent_id)
        agent_dir = self._agent_dir(agent_id)

        await self.storage.ensure_dir(workspace)
        await self.storage.ensure_dir(agent_dir)

        identity_content = req.identity or self._default_identity(agent_id, req.name, req.role)
        await self.storage.write_text(str(Path(workspace) / "IDENTITY.md"), identity_content)

        soul_content = req.soul or self._default_soul(agent_id, req.name, req.role)
        await self.storage.write_text(str(Path(workspace) / "SOUL.md"), soul_content)

        config_data = await self.gateway.get_config()
        config_hash = config_data.get("hash")
        if not config_hash:
             raise HTTPException(status_code=500, detail="Could not extract config hash")

        new_entry = {
            "id": agent_id,
            "name": req.name,
            "workspace": workspace,
            "agentDir": agent_dir,
        }
        all_agents = existing + [new_entry]
        raw = self._build_agents_raw(all_agents)

        result = await self.gateway.patch_config(config_hash, raw)

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
            workspace=workspace,
            agent_dir=agent_dir,
            status="created",
        )

    async def list_agents(self) -> List[dict[str, Any]]:
        return await self.gateway.list_agents()

    async def get_agent(self, agent_id: str) -> dict[str, Any]:
        agents = await self.gateway.list_agents()
        for a in agents:
            if a.get("id") == agent_id:
                return a
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    async def update_agent(self, agent_id: str, req: UpdateAgentRequest) -> AgentResponse:
        agent = await self.get_agent(agent_id)
        workspace = self._workspace(agent_id)

        if not await self.storage.exists(workspace):
            raise HTTPException(status_code=404, detail=f"Workspace for '{agent_id}' not found")

        if req.soul is not None:
            await self.storage.write_text(str(Path(workspace) / "SOUL.md"), req.soul)

        if req.identity is not None:
            await self.storage.write_text(str(Path(workspace) / "IDENTITY.md"), req.identity)
        elif req.name is not None or req.role is not None:
            identity_path = str(Path(workspace) / "IDENTITY.md")
            current_name = agent.get("name", "")
            current_role = ""

            if await self.storage.exists(identity_path):
                content = await self.storage.read_text(identity_path)
                for line in content.splitlines():
                    if line.startswith("Role:"):
                        current_role = line.split(":", 1)[1].strip()

            new_name = req.name if req.name is not None else current_name
            new_role = req.role if req.role is not None else current_role
            identity_content = self._default_identity(agent_id, new_name, new_role)
            await self.storage.write_text(identity_path, identity_content)

        if req.name is not None:
            config_data = await self.gateway.get_config()
            config_hash = config_data.get("hash")
            existing = await self.gateway.list_agents()
            for a in existing:
                if a.get("id") == agent_id:
                    a["name"] = req.name
                    break
            raw = self._build_agents_raw(existing)
            await self.gateway.patch_config(config_hash, raw)

        return AgentResponse(
            agent_id=agent_id,
            name=req.name or agent.get("name", ""),
            workspace=workspace,
            agent_dir=self._agent_dir(agent_id),
            status="updated",
        )

    async def delete_agent(self, agent_id: str) -> dict[str, str]:
        try:
            await self.gateway.delete_agent(agent_id)
        except Exception as exc:
            logger.warning("Gateway delete failed: %s", str(exc))

        workspace = self._workspace(agent_id)
        agent_base = str(Path(settings.OPENCLAW_STATE_DIR) / "agents" / agent_id)

        await self.storage.delete_dir(workspace)
        await self.storage.delete_dir(agent_base)

        logger.info("Agent '%s' deleted", agent_id)
        return {"status": "deleted", "agent_id": agent_id}
