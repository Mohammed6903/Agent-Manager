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

    # ── Cron ────────────────────────────────────────────────────────────────────

    async def cron_list(self) -> List[dict]:
        data = await run_openclaw(["cron", "list", "--all", "--json"])
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("jobs", "list", "payload", "data"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        return []

    async def cron_add(self, job: dict) -> dict:
        """Build CLI flags from the job dict and call `openclaw cron add`."""
        args = ["cron", "add", "--json"]

        if job.get("name"):
            args += ["--name", job["name"]]
        if job.get("agentId"):
            args += ["--agent", job["agentId"]]

        # Schedule
        schedule = job.get("schedule", {})
        kind = schedule.get("kind")
        if kind == "cron":
            args += ["--cron", schedule.get("expr", "")]
            if schedule.get("tz"):
                args += ["--tz", schedule["tz"]]
        elif kind == "every":
            args += ["--every", str(schedule.get("every", ""))]
        elif kind == "at":
            args += ["--at", schedule.get("at", "")]

        # Session target
        if job.get("sessionTarget"):
            args += ["--session", job["sessionTarget"]]

        # Payload
        payload = job.get("payload", {})
        if payload.get("kind") == "systemEvent":
            args += ["--system-event", payload.get("message", "")]
        elif payload.get("message"):
            args += ["--message", payload["message"]]

        # Enabled
        if job.get("enabled") is False:
            args.append("--disabled")

        # Delete after run
        if job.get("deleteAfterRun"):
            args.append("--delete-after-run")

        return await run_openclaw(args)

    async def cron_edit(self, job_id: str, updates: dict) -> dict:
        args = ["cron", "edit", job_id]

        if "enabled" in updates:
            args.append("--enable" if updates["enabled"] else "--disable")

        schedule = updates.get("schedule")
        if schedule:
            kind = schedule.get("kind")
            if kind == "cron" and schedule.get("expr"):
                args += ["--cron", schedule["expr"]]
                if schedule.get("tz"):
                    args += ["--tz", schedule["tz"]]
            elif kind == "every" and schedule.get("every"):
                args += ["--every", str(schedule["every"])]
            elif kind == "at" and schedule.get("at"):
                args += ["--at", schedule["at"]]

        payload = updates.get("payload")
        if payload and payload.get("message"):
            args += ["--message", payload["message"]]

        if updates.get("name"):
            args += ["--name", updates["name"]]

        return await run_openclaw(args)

    async def cron_remove(self, job_id: str) -> dict:
        return await run_openclaw(["cron", "rm", job_id, "--json"])

    async def cron_run(self, job_id: str) -> dict:
        return await run_openclaw(["cron", "run", job_id])

    async def cron_runs(self, job_id: str, limit: int = 20) -> List[dict]:
        data = await run_openclaw([
            "cron", "runs", "--id", job_id, "--limit", str(limit),
        ])
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("runs", "list", "payload", "data"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        return []
