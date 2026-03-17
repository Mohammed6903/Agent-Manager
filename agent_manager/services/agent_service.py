from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, List

from fastapi import HTTPException

from sqlalchemy.orm import Session

from ..config import settings
from ..schemas.chat import AgentResponse, CreateAgentRequest, UpdateAgentRequest
from ..repositories.storage import StorageRepository
from ..clients.gateway_client import GatewayClient
from ..repositories.agent_registry_repository import AgentRegistryRepository

logger = logging.getLogger("agent_manager.services.agent_service")

# ── Shared-file constants ───────────────────────────────────────────────────────

SHARED_DIR = Path(settings.OPENCLAW_STATE_DIR) / "shared"
SHARED_FILES = ("SOUL.md", "AGENTS.md")

class AgentService:
    def __init__(self, storage: StorageRepository, gateway: GatewayClient, db: Session = None):
        self.storage = storage
        self.gateway = gateway
        self.db = db

    @property
    def _registry(self) -> AgentRegistryRepository | None:
        return AgentRegistryRepository(self.db) if self.db else None

    def _workspace(self, agent_id: str) -> str:
        return str(Path(settings.OPENCLAW_STATE_DIR) / f"workspace-{agent_id}")

    def _agent_dir(self, agent_id: str) -> str:
        return str(Path(settings.OPENCLAW_STATE_DIR) / "agents" / agent_id / "agent")

    # ── Shared directory helpers ─────────────────────────────────────────────────

    @staticmethod
    def _shared_path(filename: str) -> str:
        """Return the absolute path to a file inside the shared directory."""
        return str(SHARED_DIR / filename)

    def _default_identity(self, agent_id: str, name: str, role: str) -> str:
        """
        Load the default identity template and fill in placeholders.
        """
        template_path = Path(__file__).parent / "../templates/IDENTITY.md"
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                template = f.read()
            return template.format(name=name, agent_id=agent_id, role=role)
        except Exception as e:
            logger.error(f"Failed to load IDENTITY.md template: {e}")
            # Fallback to a minimal identity
            return f"Name: {name}\nAgent ID: {agent_id}\nType: {role}"

    def _default_soul(self) -> str:
        """
        Load the default soul template (no per-agent placeholders).
        """
        template_path = Path(__file__).parent / "../templates/SOUL.md"
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to load SOUL.md template: {e}")
            return "# Soul\nYou are a helpful AI assistant."
        
    def _default_agents_md(self) -> str | None:
        """
        Load the default agents.md template (no per-agent placeholders).
        """
        template_path = Path(__file__).parent / "../templates/AGENTS.md"
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to load AGENTS.md template: {e}")
            return None

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

    # ── Shared-file lifecycle ────────────────────────────────────────────────────

    async def ensure_shared_files(self) -> None:
        """Bootstrap the shared directory with default templates.

        Safe to call on every startup — only writes files that do not already
        exist.
        """
        await self.storage.ensure_dir(str(SHARED_DIR))

        soul_path = self._shared_path("SOUL.md")
        if not await self.storage.exists(soul_path):
            await self.storage.write_text(soul_path, self._default_soul())
            logger.info("Bootstrapped shared SOUL.md at %s", soul_path)

        agents_path = self._shared_path("AGENTS.md")
        agents_md_content = self._default_agents_md()
        if not await self.storage.exists(agents_path) and agents_md_content:
            await self.storage.write_text(agents_path, agents_md_content)
            logger.info("Bootstrapped shared AGENTS.md at %s", agents_path)

    async def sync_templates_to_shared(self) -> dict[str, Any]:
        """Overwrite shared files with the latest source templates.

        Unlike ``ensure_shared_files`` (which skips existing files), this
        always writes the current template content so that code changes are
        propagated to every symlinked agent workspace.

        Returns a summary of what was synced and how many agents are affected.
        """
        await self.storage.ensure_dir(str(SHARED_DIR))
        results: list[dict[str, Any]] = []

        template_loaders: dict[str, Any] = {
            "SOUL.md": self._default_soul,
            "AGENTS.md": self._default_agents_md,
        }

        for filename, loader in template_loaders.items():
            content = loader()
            if content is None:
                results.append({"file": filename, "synced": False, "reason": "template not found"})
                continue

            target_path = self._shared_path(filename)
            await self.storage.write_text(target_path, content)
            affected = await self._count_symlinked_agents(filename)
            results.append({"file": filename, "synced": True, "affected_agents": affected})
            logger.info("Synced shared %s from source template — %d agent(s) affected", filename, affected)

        return {"synced_files": results}

    async def migrate_symlinks(self) -> dict[str, Any]:
        """One-time (idempotent) migration: convert regular SOUL.md / AGENTS.md
        files in every agent workspace into symlinks pointing to the shared
        copies.

        Returns a summary dict describing what was done.
        """
        results: dict[str, list[str]] = {"symlinked": [], "already_symlink": [], "errors": []}

        try:
            agents = await self.gateway.list_agents()
        except Exception as exc:
            logger.warning("migrate_symlinks: could not list agents — %s", exc)
            return {"error": str(exc)}

        for agent in agents:
            workspace = agent.get("workspace") or self._workspace(agent["id"])
            for filename in SHARED_FILES:
                link_path = str(Path(workspace) / filename)
                target_path = self._shared_path(filename)

                try:
                    if await self.storage.is_symlink(link_path):
                        results["already_symlink"].append(f"{agent['id']}/{filename}")
                        continue

                    if not await self.storage.exists(target_path):
                        results["errors"].append(
                            f"{agent['id']}/{filename}: shared file missing"
                        )
                        continue

                    # Remove the regular file and replace with a symlink
                    await self.storage.create_symlink(link_path, target_path)
                    results["symlinked"].append(f"{agent['id']}/{filename}")
                    logger.info(
                        "Migrated %s/%s → symlink to %s", agent["id"], filename, target_path
                    )
                except Exception as exc:
                    msg = f"{agent['id']}/{filename}: {exc}"
                    results["errors"].append(msg)
                    logger.error("migrate_symlinks error: %s", msg)

        return results

    async def _symlink_or_write(
        self, workspace: str, filename: str, fallback_content: str
    ) -> None:
        """Create a symlink to the shared copy of *filename* if it exists,
        otherwise fall back to writing *fallback_content* as a regular file.
        """
        link_path = str(Path(workspace) / filename)
        target_path = self._shared_path(filename)

        if await self.storage.exists(target_path):
            await self.storage.create_symlink(link_path, target_path)
            logger.info("Symlinked %s → %s", link_path, target_path)
        else:
            await self.storage.write_text(link_path, fallback_content)
            logger.info("Wrote %s (shared copy not found, using fallback)", link_path)

    # ── Agent CRUD ──────────────────────────────────────────────────────────────

    async def create_agent(self, req: CreateAgentRequest) -> AgentResponse:
        agent_id = req.agent_id
        workspace = self._workspace(agent_id)
        agent_dir = self._agent_dir(agent_id)

        # ── PHASE 1: Concurrent Network Reads ──────────────────────────────
        # Fire both gateway requests at the same time instead of waiting for one to finish
        existing_task = asyncio.create_task(self.gateway.list_agents())
        config_task = asyncio.create_task(self.gateway.get_config())
        
        existing, config_data = await asyncio.gather(existing_task, config_task)

        if any(a.get("id") == agent_id for a in existing):
            raise HTTPException(status_code=409, detail=f"Agent '{agent_id}' already exists")
        
        # Also reject if this org already has an agent with the same id in DB
        if self._registry and req.org_id:
            if self._registry.get(agent_id, org_id=req.org_id):
                raise HTTPException(status_code=409, detail=f"Agent '{agent_id}' already exists in this org")

        config_hash = config_data.get("hash")
        if not config_hash:
             raise HTTPException(status_code=500, detail="Could not extract config hash")

        agents_md_content = self._default_agents_md()
        if not agents_md_content:
            raise HTTPException(status_code=500, detail="Could not generate default AGENTS.md")

        # ── PHASE 2: Concurrent Directory Creation ─────────────────────────
        # Ensure both the workspace and agent_dir are created simultaneously
        await asyncio.gather(
            self.storage.ensure_dir(workspace),
            self.storage.ensure_dir(agent_dir)
        )

        # ── PHASE 3: Concurrent File Writing ───────────────────────────────
        # Now that directories exist, write all files and symlinks at the exact same time
        identity_content = req.identity or self._default_identity(agent_id, req.name, req.role or "")
        
        file_tasks = [
            self.storage.write_text(str(Path(workspace) / "IDENTITY.md"), identity_content),
            self._symlink_or_write(workspace, "AGENTS.md", agents_md_content)
        ]

        if req.soul:
            file_tasks.append(self.storage.write_text(str(Path(workspace) / "SOUL.md"), req.soul))
        else:
            file_tasks.append(self._symlink_or_write(workspace, "SOUL.md", self._default_soul()))

        # Execute all file writes in parallel
        await asyncio.gather(*file_tasks)

        # ── PHASE 4: Sequential Gateway Patch ──────────────────────────────
        # The patch must happen last, once the file system is fully prepped
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
        
        # PHASE 5: Write to DB registry for instant future lookups
        if self._registry:
            self._registry.create(
                agent_id=agent_id,
                name=req.name,
                workspace=workspace,
                agent_dir=agent_dir,
                org_id=req.org_id,       # None for unscoped agents
                user_id=req.user_id,
            )

        logger.info("Agent '%s' created successfully", agent_id)
        return AgentResponse(
            agent_id=agent_id,
            name=req.name,
            workspace=workspace,
            agent_dir=agent_dir,
            status="created",
            org_id=req.org_id,
        )

    async def list_agents(self, org_id: str | None = None) -> List[dict[str, Any]]:
        if self._registry:
            rows = self._registry.list(org_id=org_id)
            return [
                {
                    "id": r.agent_id,
                    "name": r.name,
                    "workspace": r.workspace,
                    "agentDir": r.agent_dir,
                    "org_id": r.org_id,
                }
                for r in rows
            ]
        # Fallback: no DB — hit gateway (org filtering not possible here)
        agents = await self.gateway.list_agents()
        return agents

    async def get_agent(self, agent_id: str, org_id: str | None = None) -> dict[str, Any]:
        # Fast path: DB registry
        if self._registry:
            row = self._registry.get(agent_id, org_id=org_id)
            if not row:
                raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
            return {
                "id": row.agent_id,
                "name": row.name,
                "workspace": row.workspace,
                "agentDir": row.agent_dir,
                "org_id": row.org_id,
            }
        # Fallback: gateway scan
        agents = await self.gateway.list_agents()
        for a in agents:
            if a.get("id") == agent_id:
                return a
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    async def update_agent(
        self, agent_id: str, req: UpdateAgentRequest, org_id: str | None = None
    ) -> AgentResponse:
        agent = await self.get_agent(agent_id, org_id=org_id)
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
            await self.storage.write_text(identity_path, self._default_identity(agent_id, new_name, new_role))

        if req.name is not None:
            config_data = await self.gateway.get_config()
            config_hash = config_data.get("hash")
            existing = await self.gateway.list_agents()
            for a in existing:
                if a.get("id") == agent_id:
                    a["name"] = req.name
                    break
            await self.gateway.patch_config(config_hash, self._build_agents_raw(existing))

            # Keep DB registry in sync
            if self._registry:
                self._registry.update_name(agent_id, req.name)

        return AgentResponse(
            agent_id=agent_id,
            name=req.name or agent.get("name", ""),
            workspace=workspace,
            agent_dir=self._agent_dir(agent_id),
            status="updated",
            org_id=org_id,
        )


    async def delete_agent(self, agent_id: str, org_id: str | None = None) -> dict[str, str]:
        # Verify ownership before deletion if org_id is supplied
        if self._registry and org_id:
            row = self._registry.get(agent_id, org_id=org_id)
            if not row:
                raise HTTPException(
                    status_code=404,
                    detail=f"Agent '{agent_id}' not found in org '{org_id}'",
                )

        # 1. Gateway removal
        try:
            await self.gateway.delete_agent(agent_id)
        except Exception as exc:
            logger.warning("Gateway delete_agent failed: %s", exc)

        # 2. DB cleanup (existing + registry row)
        if self.db:
            await self._delete_agent_db_data(agent_id)
            if self._registry:
                self._registry.delete(agent_id)

        # 3. Filesystem cleanup
        workspace = self._workspace(agent_id)
        agent_base = str(Path(settings.OPENCLAW_STATE_DIR) / "agents" / agent_id)
        await self.storage.delete_dir(workspace)
        await self.storage.delete_dir(agent_base)

        logger.info("Agent '%s' deleted (org=%s)", agent_id, org_id)
        return {"status": "deleted", "agent_id": agent_id}

    async def _delete_agent_db_data(self, agent_id: str) -> None:
        """Remove every database record associated with the agent."""
        from sqlalchemy import delete as sa_delete
        from ..models.gmail import GoogleAccount, AgentSecret
        from ..models.agent_task import AgentTask
        from ..repositories.integration_repository import IntegrationRepository
        from ..repositories.cron_ownership_repository import CronOwnershipRepository
        from ..repositories.context_repository import ContextRepository

        # -- Cron jobs: remove from gateway first, then ownership/pipeline rows --
        cron_repo = CronOwnershipRepository(self.db)
        cron_ids = cron_repo.delete_by_agent_id(agent_id)
        for cron_id in cron_ids:
            try:
                await self.gateway.cron_remove(cron_id)
            except Exception as exc:
                logger.warning("cron_remove(%s) failed during agent delete: %s", cron_id, exc)

        # -- Integration assignments + logs --
        IntegrationRepository(self.db).delete_all_for_agent(agent_id)

        # -- Context assignments (not the shared global contexts themselves) --
        ContextRepository(self.db).delete_agent_context_assignments(agent_id)

        # -- Agent tasks --
        self.db.execute(sa_delete(AgentTask).where(AgentTask.agent_id == agent_id))

        # -- Google OAuth tokens --
        self.db.execute(sa_delete(GoogleAccount).where(GoogleAccount.agent_id == agent_id))

        # -- All secrets (API keys, OAuth credentials) --
        self.db.execute(sa_delete(AgentSecret).where(AgentSecret.agent_id == agent_id))

        self.db.commit()
        logger.info("DB data purged for agent '%s'", agent_id)

    # ── Shared-file admin helpers ────────────────────────────────────────────────

    async def update_shared_file(self, filename: str, content: str) -> dict[str, Any]:
        """Write *content* to the shared copy of *filename* and return how many
        agent workspaces will see the change (i.e. have a symlink pointing to
        it).
        """
        if filename not in SHARED_FILES:
            raise HTTPException(
                status_code=400,
                detail=f"Only {', '.join(SHARED_FILES)} can be updated via this endpoint.",
            )
        target_path = self._shared_path(filename)
        await self.storage.write_text(target_path, content)
        affected = await self._count_symlinked_agents(filename)
        logger.info("Updated shared %s — %d agent(s) affected", filename, affected)
        return {"filename": filename, "affected_agents": affected}

    async def _count_symlinked_agents(self, filename: str) -> int:
        """Count how many existing agent workspaces have a symlink for *filename*."""
        count = 0
        try:
            agents = await self.gateway.list_agents()
        except Exception:
            return 0
        for agent in agents:
            workspace = agent.get("workspace") or self._workspace(agent["id"])
            link_path = str(Path(workspace) / filename)
            try:
                if await self.storage.is_symlink(link_path):
                    count += 1
            except Exception:
                pass
        return count
    
    async def sync_agents_to_registry(self, org_id: str | None = None) -> dict[str, Any]:
        """
        One-time (idempotent) migration: pull all agents from the gateway and
        upsert them into the DB registry.  Safe to call repeatedly.

        If org_id is provided it is stamped on every row that doesn't already
        have one — useful when you know all agents on disk belong to one org.
        """
        if not self._registry:
            raise HTTPException(status_code=500, detail="DB not available for registry sync")

        agents = await self.gateway.list_agents()
        created, updated, skipped = [], [], []

        for a in agents:
            agent_id = a.get("id")
            if not agent_id:
                skipped.append({"agent": a, "reason": "missing id"})
                continue

            workspace = a.get("workspace") or self._workspace(agent_id)
            agent_dir = a.get("agentDir") or self._agent_dir(agent_id)

            existing = self._registry.get(agent_id)   # intentionally unscoped — check by agent_id only
            if existing:
                # Only backfill org_id if it's currently unset and caller supplied one
                if org_id and not existing.org_id:
                    self._registry.db.query(__import__(
                        "..models.agent_registry", fromlist=["AgentRegistry"]
                    ).AgentRegistry).filter_by(agent_id=agent_id).update({"org_id": org_id})
                    self._registry.db.commit()
                    updated.append(agent_id)
                else:
                    skipped.append({"agent_id": agent_id, "reason": "already in registry"})
                continue

            self._registry.create(
                agent_id=agent_id,
                name=a.get("name", agent_id),
                workspace=workspace,
                agent_dir=agent_dir,
                org_id=org_id,
            )
            created.append(agent_id)
            logger.info("sync_agents_to_registry: registered '%s' (org=%s)", agent_id, org_id)

        logger.info(
            "Registry sync complete — created=%d updated=%d skipped=%d",
            len(created), len(updated), len(skipped),
        )
        return {"created": created, "updated": updated, "skipped": skipped}
