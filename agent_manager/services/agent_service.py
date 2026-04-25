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
from ..repositories.subscription_repository import SubscriptionRepository

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

    @property
    def _sub_repo(self) -> SubscriptionRepository | None:
        return SubscriptionRepository(self.db) if self.db else None

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
        """Overwrite shared files AND push copies to every agent workspace.

        Since OpenClaw cannot read symlinks, we write the actual file content
        directly into each agent's workspace on every startup.
        """
        await self.storage.ensure_dir(str(SHARED_DIR))
        results: list[dict[str, Any]] = []

        template_loaders: dict[str, Any] = {
            "SOUL.md": self._default_soul,
            "AGENTS.md": self._default_agents_md,
        }

        try:
            agents = await self.gateway.list_agents()
        except Exception:
            agents = []

        for filename, loader in template_loaders.items():
            content = loader()
            if content is None:
                results.append({"file": filename, "synced": False, "reason": "template not found"})
                continue

            # Write to shared dir (canonical copy)
            target_path = self._shared_path(filename)
            await self.storage.write_text(target_path, content)

            # Push to every agent workspace
            affected = 0
            for agent in agents:
                workspace = agent.get("workspace") or self._workspace(agent["id"])
                dest = str(Path(workspace) / filename)
                try:
                    await self.storage.write_text(dest, content)
                    affected += 1
                except Exception as exc:
                    logger.warning("Failed to sync %s to %s: %s", filename, workspace, exc)

            results.append({"file": filename, "synced": True, "affected_agents": affected})
            logger.info("Synced shared %s from source template — %d agent(s) affected", filename, affected)

        return {"synced_files": results}

    async def migrate_symlinks(self) -> dict[str, Any]:
        """One-time (idempotent) migration: copy shared SOUL.md / AGENTS.md
        into every agent workspace (replacing any stale symlinks or outdated
        copies).

        Returns a summary dict describing what was done.
        """
        results: dict[str, list[str]] = {"copied": [], "already_current": [], "errors": []}

        try:
            agents = await self.gateway.list_agents()
        except Exception as exc:
            logger.warning("migrate_symlinks: could not list agents — %s", exc)
            return {"error": str(exc)}

        for agent in agents:
            workspace = agent.get("workspace") or self._workspace(agent["id"])
            for filename in SHARED_FILES:
                dest_path = str(Path(workspace) / filename)
                target_path = self._shared_path(filename)

                try:
                    if not await self.storage.exists(target_path):
                        results["errors"].append(
                            f"{agent['id']}/{filename}: shared file missing"
                        )
                        continue

                    # Read the shared file and write its content to the workspace
                    content = await self.storage.read_text(target_path)
                    await self.storage.write_text(dest_path, content)
                    results["copied"].append(f"{agent['id']}/{filename}")
                    logger.info(
                        "Copied shared %s into %s/%s", target_path, agent["id"], filename
                    )
                except Exception as exc:
                    msg = f"{agent['id']}/{filename}: {exc}"
                    results["errors"].append(msg)
                    logger.error("migrate_symlinks error: %s", msg)

        return results

    async def _copy_shared_or_write(
        self, workspace: str, filename: str, fallback_content: str
    ) -> None:
        """Copy the shared file into the agent workspace.

        Uses direct file copies instead of symlinks because OpenClaw
        cannot read symlinked files reliably.
        """
        dest_path = str(Path(workspace) / filename)
        target_path = self._shared_path(filename)

        if await self.storage.exists(target_path):
            content = await self.storage.read_text(target_path)
            await self.storage.write_text(dest_path, content)
            logger.info("Copied shared %s → %s", target_path, dest_path)
        else:
            await self.storage.write_text(dest_path, fallback_content)
            logger.info("Wrote %s (shared copy not found, using fallback)", dest_path)

    # ── Agent CRUD ──────────────────────────────────────────────────────────────

    async def create_agent(self, req: CreateAgentRequest) -> AgentResponse:
        agent_id = req.agent_id
        workspace = self._workspace(agent_id)
        agent_dir = self._agent_dir(agent_id)

        # ── PRE-FLIGHT: Check wallet balance before doing any work ───────
        # Only runs when the $24/mo subscription model is enforced. In
        # pay-as-you-go mode this check is skipped entirely — agent
        # creation is free, and users are only charged for actual token
        # usage at chat time via the wallet balance gate in
        # chat_service._check_wallet_balance.
        if (
            settings.ENFORCE_AGENT_SUBSCRIPTION
            and req.org_id
            and req.user_id
        ):
            from ..clients.wallet_client import get_wallet_client
            wallet = get_wallet_client(agent_id)
            try:
                balance_resp = await wallet.check_balance(req.user_id)
                balance_data = balance_resp.get("data", balance_resp)
                balance_cents = balance_data.get("balanceCents", 0)
                if balance_cents < settings.AGENT_MONTHLY_COST_CENTS:
                    raise HTTPException(
                        status_code=402,
                        detail=f"Insufficient balance. ${settings.AGENT_MONTHLY_COST_CENTS / 100:.2f} required to create an agent.",
                    )
            except HTTPException:
                raise
            except Exception as exc:
                logger.warning("Wallet pre-flight check failed (allowing request): %s", exc)

        # ── PHASE 1: Gateway Read ──────────────────────────────────────────
        # Single round-trip: list_agents for the 409 duplicate check.
        # No more get_config — agents.create resolves its own config hash
        # internally, so we don't need to ferry one through.
        existing = await self.gateway.list_agents()

        if any(a.get("id") == agent_id for a in existing):
            raise HTTPException(status_code=409, detail=f"Agent '{agent_id}' already exists")

        # Also reject if the agent already exists under the same ownership scope.
        # These `get()` calls filter out soft-deleted rows by default, so a
        # previously-deleted agent with the same id doesn't trip the 409.
        if self._registry:
            if req.org_id and self._registry.get(agent_id, org_id=req.org_id):
                raise HTTPException(status_code=409, detail=f"Agent '{agent_id}' already exists in this org")
            if req.user_id and self._registry.get(agent_id, user_id=req.user_id):
                raise HTTPException(status_code=409, detail=f"Agent '{agent_id}' already exists for this user")

            # If a soft-deleted row with this exact agent_id exists (in ANY
            # ownership scope — agent_ids are globally unique via the
            # unique constraint on the table), we can't INSERT a new row
            # with the same id. Return a structured 409 pointing the
            # caller at the restore endpoint so they can recover the
            # deleted agent instead. Silently auto-restoring would be
            # surprising if they wanted a fresh agent, so we require an
            # explicit decision.
            soft_deleted = self._registry.get(agent_id, include_deleted=True)
            if soft_deleted is not None and soft_deleted.deleted_at is not None:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "agent_soft_deleted",
                        "message": (
                            f"Agent '{agent_id}' was previously deleted and is "
                            f"recoverable. POST /api/agents/{agent_id}/restore "
                            f"to bring it back, or choose a different id."
                        ),
                        "agent_id": agent_id,
                        "deleted_at": soft_deleted.deleted_at.isoformat(),
                    },
                )

        agents_md_content = self._default_agents_md()
        if not agents_md_content:
            raise HTTPException(status_code=500, detail="Could not generate default AGENTS.md")

        # ── PHASE 2: Concurrent Directory Creation ─────────────────────────
        # Ensure both the workspace and agent_dir are created simultaneously
        await asyncio.gather(
            self.storage.ensure_dir(workspace),
            self.storage.ensure_dir(agent_dir)
        )

        # ── PHASE 3: Concurrent SOUL.md / AGENTS.md write ──────────────────
        # IDENTITY.md is written AFTER agents.create — see PHASE 5. The
        # gateway's agents.create handler appends a ``- Name:`` stanza to
        # IDENTITY.md, so writing our full template before would lose to
        # the gateway's append; writing after guarantees our content wins.
        identity_content = req.identity or self._default_identity(agent_id, req.name, req.role or "")

        file_tasks = [
            self._copy_shared_or_write(workspace, "AGENTS.md", agents_md_content)
        ]

        if req.soul:
            file_tasks.append(self.storage.write_text(str(Path(workspace) / "SOUL.md"), req.soul))
        else:
            file_tasks.append(self._copy_shared_or_write(workspace, "SOUL.md", self._default_soul()))

        await asyncio.gather(*file_tasks)

        # ── PHASE 4: Gateway agent registration (no restart) ───────────────
        # agents.create + agents.update hot-apply via writeConfigFile's
        # in-memory refresh — no SIGUSR1, no downtime. Replaces the old
        # config.patch path which respawned the Node process.
        await self.gateway.create_agent_record(
            agent_id=agent_id,
            name=req.name,
            workspace=workspace,
        )

        # ── PHASE 5: Overwrite IDENTITY.md with our template ───────────────
        await self.storage.write_text(str(Path(workspace) / "IDENTITY.md"), identity_content)
        
        # PHASE 5: Write to DB registry for instant future lookups
        if self._registry:
            self._registry.create(
                agent_id=agent_id,
                name=req.name,
                workspace=workspace,
                agent_dir=agent_dir,
                org_id=req.org_id,       # None for unscoped agents
                user_id=req.user_id,
                # Agent type + Q&A config. ``agent_type`` falls through
                # to the model's server_default ("default") when None,
                # and the four qa_* columns are only populated for
                # Q&A agents. Already validated at the schema layer.
                agent_type=req.agent_type,
                qa_welcome_message=req.qa_welcome_message,
                qa_persona_instructions=req.qa_persona_instructions,
                qa_page_title=req.qa_page_title,
                qa_page_subtitle=req.qa_page_subtitle,
                llm_model=req.llm_model,
            )

        # PHASE 6: Create subscription and deduct initial $24.
        # Gated on settings.ENFORCE_AGENT_SUBSCRIPTION so pay-as-you-go mode
        # skips the monthly charge entirely. Users still pay for actual
        # token usage via the wallet — that's handled in the chat path.
        if (
            settings.ENFORCE_AGENT_SUBSCRIPTION
            and self.db
            and req.org_id
            and req.user_id
        ):
            from .subscription_service import SubscriptionService
            sub_svc = SubscriptionService(self.db)
            try:
                await sub_svc.create_subscription(agent_id, req.org_id, req.user_id)
            except Exception as exc:
                # Rollback: remove registry entry, gateway agent, and filesystem
                logger.error("Subscription creation failed for '%s', rolling back: %s", agent_id, exc)
                if self._registry:
                    self._registry.delete(agent_id)
                try:
                    await self.gateway.delete_agent(agent_id)
                except Exception:
                    pass
                await self.storage.delete_dir(workspace)
                await self.storage.delete_dir(str(Path(settings.OPENCLAW_STATE_DIR) / "agents" / agent_id))
                raise

        logger.info("Agent '%s' created successfully (type=%s)", agent_id, req.agent_type or "default")
        return AgentResponse(
            agent_id=agent_id,
            name=req.name,
            workspace=workspace,
            agent_dir=agent_dir,
            status="created",
            org_id=req.org_id,
            user_id=req.user_id,
            agent_type=req.agent_type or "default",
            qa_welcome_message=req.qa_welcome_message,
            qa_persona_instructions=req.qa_persona_instructions,
            qa_page_title=req.qa_page_title,
            qa_page_subtitle=req.qa_page_subtitle,
            llm_model=req.llm_model,
        )

    async def list_agents(self, org_id: str | None = None, user_id: str | None = None) -> List[dict[str, Any]]:
        if self._registry:
            # Registry filters soft-deleted rows (deleted_at IS NULL) by
            # default — no cross-table join needed. This works identically
            # regardless of whether ENFORCE_AGENT_SUBSCRIPTION is on.
            rows = self._registry.list(org_id=org_id, user_id=user_id)

            result = []
            for r in rows:
                entry: dict[str, Any] = {
                    "id": r.agent_id,
                    "name": r.name,
                    "workspace": r.workspace,
                    "agentDir": r.agent_dir,
                    "org_id": r.org_id,
                    "user_id": r.user_id,
                    # Surface type + Q&A config so the frontend can
                    # render type badges on list rows and show the
                    # copy-link button on Q&A agents without an
                    # extra round trip.
                    "agent_type": r.agent_type,
                    "qa_welcome_message": r.qa_welcome_message,
                    "qa_page_title": r.qa_page_title,
                    "qa_page_subtitle": r.qa_page_subtitle,
                    "llm_model": r.llm_model,
                    # NOTE: intentionally omitting qa_persona_instructions
                    # from list responses — it's a potentially long
                    # field and only needed when editing a single agent,
                    # not when rendering a list row.
                }
                # Include subscription status when available so the frontend
                # can still render the "locked" badge if subscriptions are
                # enforced. None when the flag is off and no row exists.
                if self._sub_repo:
                    sub = self._sub_repo.get_by_agent_id(r.agent_id)
                    if sub:
                        entry["subscription_status"] = sub.status
                result.append(entry)
            return result
        # Fallback: no DB — hit gateway (org/user filtering not possible here)
        agents = await self.gateway.list_agents()
        return agents

    async def get_agent(self, agent_id: str, org_id: str | None = None, user_id: str | None = None) -> dict[str, Any]:
        # Fast path: DB registry. Soft-deleted rows are filtered by the
        # repository (deleted_at IS NULL), so asking for a deleted agent
        # returns 404 — the agent is invisible until restored.
        if self._registry:
            row = self._registry.get(agent_id, org_id=org_id, user_id=user_id)
            if not row:
                raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

            result: dict[str, Any] = {
                "id": row.agent_id,
                "name": row.name,
                "workspace": row.workspace,
                "agentDir": row.agent_dir,
                "org_id": row.org_id,
                "user_id": row.user_id,
                # Full type + Q&A config on single-agent fetches. This
                # is what the agent detail / edit view consumes, so
                # ``qa_persona_instructions`` is included here (unlike
                # the list view which omits it for payload size).
                "agent_type": row.agent_type,
                "qa_welcome_message": row.qa_welcome_message,
                "qa_persona_instructions": row.qa_persona_instructions,
                "qa_page_title": row.qa_page_title,
                "qa_page_subtitle": row.qa_page_subtitle,
                "llm_model": row.llm_model,
            }
            if self._sub_repo:
                sub = self._sub_repo.get_by_agent_id(agent_id)
                if sub:
                    result["subscription_status"] = sub.status
            return result
        # Fallback: gateway scan
        agents = await self.gateway.list_agents()
        for a in agents:
            if a.get("id") == agent_id:
                return a
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    async def update_agent(
        self, agent_id: str, req: UpdateAgentRequest, org_id: str | None = None, user_id: str | None = None
    ) -> AgentResponse:
        agent = await self.get_agent(agent_id, org_id=org_id, user_id=user_id)

        # Block updates for deleted agents (always) and locked agents
        # (only when the subscription model is enforced). With
        # ENFORCE_AGENT_SUBSCRIPTION=False, locked agents are still usable
        # so we don't gate updates on that state either.
        if self._sub_repo:
            sub = self._sub_repo.get_by_agent_id(agent_id)
            if sub and sub.status == "deleted":
                raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
            if (
                sub
                and sub.status == "locked"
                and settings.ENFORCE_AGENT_SUBSCRIPTION
            ):
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "agent_locked",
                        "message": "Agent is locked due to unpaid subscription. Please add credits to unlock.",
                    },
                )

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

        if req.name is not None or req.llm_model is not None:
            await self.gateway.update_agent_record(
                agent_id=agent_id,
                name=req.name,
                model=req.llm_model,
            )

            # Keep DB registry in sync
            if self._registry:
                if req.name is not None:
                    self._registry.update_name(agent_id, req.name)
                if req.llm_model is not None:
                    self._registry.update_llm_model(agent_id, req.llm_model)

        # Persist agent_type + Q&A config changes. Only touches columns
        # the caller actually passed (each None value is preserved
        # via the repository's selective-update pattern).
        if self._registry and any(
            getattr(req, f) is not None
            for f in (
                "agent_type",
                "qa_welcome_message",
                "qa_persona_instructions",
                "qa_page_title",
                "qa_page_subtitle",
            )
        ):
            self._registry.update_qa_config(
                agent_id=agent_id,
                agent_type=req.agent_type,
                qa_welcome_message=req.qa_welcome_message,
                qa_persona_instructions=req.qa_persona_instructions,
                qa_page_title=req.qa_page_title,
                qa_page_subtitle=req.qa_page_subtitle,
            )

        # Re-read the row so the response reflects the final state
        # including any QA fields we just persisted (the call to
        # ``get_agent`` above captures the pre-update state).
        updated_row = self._registry.get(agent_id) if self._registry else None

        return AgentResponse(
            agent_id=agent_id,
            name=req.name or agent.get("name", ""),
            workspace=workspace,
            agent_dir=self._agent_dir(agent_id),
            status="updated",
            org_id=org_id,
            user_id=user_id,
            agent_type=(updated_row.agent_type if updated_row else agent.get("agent_type")),
            qa_welcome_message=(updated_row.qa_welcome_message if updated_row else agent.get("qa_welcome_message")),
            qa_persona_instructions=(updated_row.qa_persona_instructions if updated_row else agent.get("qa_persona_instructions")),
            qa_page_title=(updated_row.qa_page_title if updated_row else agent.get("qa_page_title")),
            qa_page_subtitle=(updated_row.qa_page_subtitle if updated_row else agent.get("qa_page_subtitle")),
            llm_model=(updated_row.llm_model if updated_row else agent.get("llm_model")),
        )


    async def delete_agent(self, agent_id: str, org_id: str | None = None, user_id: str | None = None) -> dict[str, str]:
        """Soft-delete an agent.

        The agent is marked deleted in the registry (``deleted_at``
        stamped) but all data is preserved on disk and in the DB so it
        can be restored later via ``restore_agent``. The openclaw
        gateway config is updated to stop serving the agent, and any
        cron jobs it owned are cancelled. If the subscription model is
        enforced, the subscription row is also marked deleted for
        back-compat with the recovery-via-unlock flow.
        """
        # Verify ownership before deletion if org_id or user_id is supplied.
        # Skip deleted rows — asking to delete a deleted agent is a 404.
        if self._registry and (org_id or user_id):
            row = self._registry.get(agent_id, org_id=org_id, user_id=user_id)
            if not row:
                raise HTTPException(
                    status_code=404,
                    detail=f"Agent '{agent_id}' not found for the given ownership scope",
                )

        if self.db:
            # Disable cron jobs so nothing schedules against a deleted agent.
            from ..models.cron import CronOwnership
            cron_ids = [
                c.cron_id
                for c in self.db.query(CronOwnership)
                .filter(CronOwnership.agent_id == agent_id)
                .all()
            ]
            for cron_id in cron_ids:
                try:
                    await self.gateway.cron_remove(cron_id)
                except Exception as exc:
                    logger.warning("cron_remove(%s) failed during delete: %s", cron_id, exc)

            # Soft-delete at the registry layer. This is the single
            # source of truth for "is this agent visible?" — independent
            # of the subscription model so it works whether or not
            # ENFORCE_AGENT_SUBSCRIPTION is on.
            if self._registry:
                self._registry.soft_delete(agent_id)

            # If the subscription model is enforced, also mark the
            # subscription row deleted so the old unlock-based recovery
            # flow stays consistent. No-op when the flag is off (no row).
            if settings.ENFORCE_AGENT_SUBSCRIPTION and self._sub_repo:
                sub = self._sub_repo.get_by_agent_id(agent_id)
                if sub:
                    self._sub_repo.soft_delete(agent_id)

        # Remove from openclaw gateway so the agent stops serving requests.
        # The registry row is still in our DB for restore, but the gateway
        # config shouldn't advertise the agent while it's deleted.
        try:
            await self.gateway.delete_agent(agent_id)
        except Exception as exc:
            logger.warning("Gateway delete_agent failed: %s", exc)

        logger.info("Agent '%s' soft-deleted (org=%s)", agent_id, org_id)
        return {"status": "deleted", "agent_id": agent_id}

    async def restore_agent(
        self,
        agent_id: str,
        org_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, str]:
        """Restore a previously soft-deleted agent.

        Clears ``deleted_at`` on the registry row, re-registers the
        agent with the openclaw gateway, and (if the subscription model
        is enforced) restores the subscription row to ``active``.

        Returns 404 if no soft-deleted agent with this ID exists for the
        given ownership scope.
        """
        if not self._registry or not self.db:
            raise HTTPException(
                status_code=500,
                detail="Registry not configured — cannot restore agents",
            )

        # Find the deleted row — must include deleted or we can't see it
        row = self._registry.get(
            agent_id,
            org_id=org_id,
            user_id=user_id,
            include_deleted=True,
        )
        if not row or row.deleted_at is None:
            raise HTTPException(
                status_code=404,
                detail=f"No deleted agent '{agent_id}' to restore",
            )

        # Flip deleted_at back to NULL
        self._registry.restore(agent_id)

        # If subscription enforcement is on, reactivate the subscription
        # row so the chat/update gates let the agent back through.
        if settings.ENFORCE_AGENT_SUBSCRIPTION and self._sub_repo:
            sub = self._sub_repo.get_by_agent_id(agent_id)
            if sub and sub.status == "deleted":
                # Mark it active again. Exact transition depends on the
                # repo's API — we use the existing mark_active helper if
                # available, otherwise fall back to a direct status write.
                mark_active = getattr(self._sub_repo, "mark_active", None)
                if callable(mark_active):
                    mark_active(agent_id)
                else:
                    from ..models.agent_subscription import AgentSubscription
                    self.db.query(AgentSubscription).filter(
                        AgentSubscription.agent_id == agent_id
                    ).update({"status": "active", "deleted_at": None})
                    self.db.commit()

        # Re-register with the openclaw gateway so it shows up again.
        # Uses agents.create (no SIGUSR1 restart) — same path as create_agent.
        # If the gateway still has the row cached, agents.create returns
        # "already exists" which we swallow as success.
        try:
            await self.gateway.create_agent_record(
                agent_id=agent_id,
                name=row.name,
                workspace=row.workspace or self._workspace(agent_id),
            )
        except Exception as exc:
            if "already exists" not in str(exc).lower():
                logger.warning(
                    "Gateway re-register failed during restore of '%s': %s",
                    agent_id,
                    exc,
                )

        logger.info("Agent '%s' restored (org=%s)", agent_id, org_id)
        return {"status": "restored", "agent_id": agent_id}

    async def _delete_agent_db_data(self, agent_id: str) -> None:
        """Remove operational database records associated with the agent.

        Analytics / usage / billing tables are intentionally preserved:
        - chat_usage_logs      (token usage & cost per message)
        - wallet_transactions  (credit movements)
        - integration_logs     (API call history)
        - cron_pipeline_runs   (pipeline run history & costs)
        """
        from sqlalchemy import delete as sa_delete
        from ..models.gmail import GoogleAccount, AgentSecret
        from ..models.agent_task import AgentTask
        from ..repositories.integration_repository import IntegrationRepository
        from ..repositories.cron_ownership_repository import CronOwnershipRepository
        from ..repositories.context_repository import ContextRepository

        # -- Cron jobs: remove from gateway first, then ownership rows --
        # CronPipelineRun rows are preserved (FK set to NULL on cron delete)
        cron_repo = CronOwnershipRepository(self.db)
        cron_ids = cron_repo.delete_by_agent_id(agent_id)
        for cron_id in cron_ids:
            try:
                await self.gateway.cron_remove(cron_id)
            except Exception as exc:
                logger.warning("cron_remove(%s) failed during agent delete: %s", cron_id, exc)

        # -- Integration assignments (logs are preserved for analytics) --
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
        """Write *content* to the shared copy of *filename* and push it to
        every agent workspace.
        """
        if filename not in SHARED_FILES:
            raise HTTPException(
                status_code=400,
                detail=f"Only {', '.join(SHARED_FILES)} can be updated via this endpoint.",
            )
        target_path = self._shared_path(filename)
        await self.storage.write_text(target_path, content)

        # Push the updated content to every agent workspace
        try:
            agents = await self.gateway.list_agents()
        except Exception:
            agents = []

        affected = 0
        for agent in agents:
            workspace = agent.get("workspace") or self._workspace(agent["id"])
            dest = str(Path(workspace) / filename)
            try:
                await self.storage.write_text(dest, content)
                affected += 1
            except Exception as exc:
                logger.warning("Failed to push %s to %s: %s", filename, workspace, exc)

        logger.info("Updated shared %s — %d agent(s) affected", filename, affected)
        return {"filename": filename, "affected_agents": affected}

    async def _count_agents_with_file(self, filename: str) -> int:
        """Count how many existing agent workspaces have *filename*."""
        count = 0
        try:
            agents = await self.gateway.list_agents()
        except Exception:
            return 0
        for agent in agents:
            workspace = agent.get("workspace") or self._workspace(agent["id"])
            file_path = str(Path(workspace) / filename)
            try:
                if await self.storage.exists(file_path):
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
