import json
import logging
from typing import Any, List
from .gateway_client import GatewayClient
from ..openclaw import run_openclaw

logger = logging.getLogger("agent_manager.clients.cli_gateway_client")

class CLIGatewayClient(GatewayClient):
    async def list_agents(self) -> List[dict]:
        data = await run_openclaw(["agents", "list", "--json"])
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("agents", "list", "payload", "data"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            if "id" in data:
                return [data]
        return []

    async def get_config(self) -> dict:
        return await run_openclaw(["gateway", "call", "config.get", "--params", "{}", "--json"])

    async def patch_config(self, base_hash: str, raw_config: str) -> dict:
        params = json.dumps({"baseHash": base_hash, "raw": raw_config})
        return await run_openclaw(["gateway", "call", "config.patch", "--params", params, "--json"])

    async def delete_agent(self, agent_id: str) -> dict:
        return await run_openclaw(["agents", "delete", agent_id, "--force", "--json"])

    async def get_status(self) -> dict:
        return await run_openclaw(["gateway", "status", "--json"])
