"""Service layer for ThirdPartyContext creation and management."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..celery_app import celery_app
from ..repositories.integration_repository import IntegrationRepository
from ..repositories.third_party_context_repository import ThirdPartyContextRepository
from ..repositories.third_party_context_assignment_repository import (
    ThirdPartyContextAssignmentRepository,
)
from ..services.agent_service import AgentService
from ..services.context_providers import get_provider

logger = logging.getLogger(__name__)


class ThirdPartyContextService:
    """Orchestrates validation and task dispatch for third-party context jobs."""

    def __init__(self, db: Session, agent_service: AgentService | None = None) -> None:
        self.db = db
        self.agent_service = agent_service

    async def _enrich_context(self, ctx: any, org_id: str | None = None) -> dict:
        """Add mapped_agents (ID + Name) to a context object/row."""
        assign_repo = ThirdPartyContextAssignmentRepository(self.db)
        mappings = assign_repo.get_assignments_for_context(ctx.id)
        mapped_ids = [m.agent_id for m in mappings]

        # Fetch names from agent_service if available
        agent_map = {}
        if self.agent_service:
            try:
                all_agents = await self.agent_service.list_agents(org_id=org_id)
                agent_map = {a["id"]: a["name"] for a in all_agents}
            except Exception as e:
                logger.warning("Could not fetch agent names for enrichment: %s", e)

        # Convert SQLAlchemy model to dict if it isn't already
        if hasattr(ctx, "__dict__"):
            data = {
                "id": ctx.id,
                "agent_id": ctx.agent_id,
                "integration_name": ctx.integration_name,
                "integration_metadata": ctx.integration_metadata,
                "celery_task_id": ctx.celery_task_id,
                "status": ctx.status,
                "created_at": ctx.created_at,
                "updated_at": ctx.updated_at,
            }
        else:
            data = dict(ctx)

        data["mapped_agents"] = [
            {"agent_id": aid, "name": agent_map.get(aid, "Unknown Agent")}
            for aid in mapped_ids
        ]
        return data

    # ── Generic context creation / deletion ───────────────────────────────

    async def create_context(
        self, integration_name: str, agent_id: str, force_full_sync: bool = False,
    ) -> dict:
        """Validate credentials, create a tracking row, and enqueue the sync task.

        Works for any registered integration — no per-integration methods needed.
        """
        provider = get_provider(integration_name)
        if not provider:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown integration: {integration_name}",
            )

        ctx_repo = ThirdPartyContextRepository(self.db)

        # Check for a truly active task for THIS integration/agent pair
        active_ctx = ctx_repo.get_active_by_agent_and_integration(agent_id, integration_name)
        if active_ctx and active_ctx.celery_task_id:
            state = celery_app.AsyncResult(active_ctx.celery_task_id).state
            terminal = ("SUCCESS", "FAILURE", "REVOKED", "TASK_ERROR", "TASK_CANCELLED")

            # Celery returns "PENDING" for unknown/lost tasks — treat a
            # PENDING task older than 10 minutes as dead so we don't deadlock.
            _STALE_THRESHOLD = timedelta(minutes=10)
            is_stale = (
                state == "PENDING"
                and active_ctx.updated_at is not None
                and (datetime.now(timezone.utc) - active_ctx.updated_at.replace(tzinfo=timezone.utc))
                > _STALE_THRESHOLD
            )

            if is_stale:
                logger.warning(
                    "Marking stale %s context %s (task %s) as failed — "
                    "Celery state PENDING for >%s.",
                    integration_name, active_ctx.id,
                    active_ctx.celery_task_id, _STALE_THRESHOLD,
                )
                ctx_repo.update_status(active_ctx.id, "failed")
            elif state not in terminal:
                return {
                    "task_id": active_ctx.celery_task_id,
                    "context_id": str(active_ctx.id),
                    "message": f"{provider.display_name} sync already in progress. Resuming view.",
                }

        # Verify integration assignment
        assignment = IntegrationRepository(self.db).get_assignment(agent_id, integration_name)
        if not assignment:
            raise HTTPException(
                status_code=400,
                detail=f"{provider.display_name} integration not assigned to agent.",
            )

        # Verify credentials
        if not provider.verify_credentials(self.db, agent_id):
            raise HTTPException(
                status_code=400,
                detail=f"{provider.display_name} credentials invalid/expired.",
            )

        ctx = ctx_repo.create(
            agent_id=agent_id,
            integration_name=integration_name,
            metadata=assignment.integration_metadata,
        )

        # Automatically assign the creator so they appear in mapped_agents
        assign_repo = ThirdPartyContextAssignmentRepository(self.db)
        assign_repo.assign(ctx.id, agent_id)

        task = provider.get_ingest_task().delay(
            agent_id, str(ctx.id), force_full_sync,
            integration_name=integration_name,
        )
        ctx_repo.update_task(ctx.id, task.id, "ingesting")

        return {
            "task_id": task.id,
            "context_id": str(ctx.id),
            "message": f"Background {provider.display_name} sync started.",
        }

    async def purge_context_data(self, context_id: uuid.UUID) -> dict:
        """Enqueue background deletion of context data for any integration."""
        ctx_repo = ThirdPartyContextRepository(self.db)
        context = ctx_repo.get(context_id)
        if not context:
            raise HTTPException(status_code=404, detail="Context not found")

        provider = get_provider(context.integration_name)
        if not provider:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown integration: {context.integration_name}",
            )

        task = provider.get_delete_task().delay(
            context.agent_id, str(context_id),
            integration_name=context.integration_name,
        )
        ctx_repo.update_task(context_id, task.id, "deleting")

        return {
            "task_id": task.id,
            "context_id": str(context_id),
            "message": "Background delete started.",
        }

    # ── Read / list / assign ──────────────────────────────────────────────

    async def get_context(self, context_id: uuid.UUID, org_id: str | None = None) -> dict:
        """Fetch a single ThirdPartyContext by ID with its mappings."""
        ctx_repo = ThirdPartyContextRepository(self.db)
        ctx = ctx_repo.get(context_id)
        if not ctx:
            raise HTTPException(status_code=404, detail="Context not found")
        return await self._enrich_context(ctx, org_id=org_id)

    async def list_contexts_for_agent(self, agent_id: str, org_id: str | None = None) -> list:
        """Return all ThirdPartyContext rows assigned to an agent."""
        assign_repo = ThirdPartyContextAssignmentRepository(self.db)
        contexts = assign_repo.get_contexts_for_agent(agent_id)
        return [await self._enrich_context(c, org_id=org_id) for c in contexts]

    async def get_all_complete_contexts(self, org_id: str | None = None) -> list:
        ctx_repo = ThirdPartyContextRepository(self.db)
        contexts = ctx_repo.get_all_complete()

        # Filter to only contexts whose creator agent belongs to the org
        if org_id:
            from ..repositories.agent_registry_repository import AgentRegistryRepository
            org_agent_ids = {
                r.agent_id for r in AgentRegistryRepository(self.db).list(org_id=org_id)
            }
            contexts = [c for c in contexts if c.agent_id in org_agent_ids]

        return [await self._enrich_context(c, org_id=org_id) for c in contexts]

    async def get_available_agents(self, context_id: uuid.UUID, org_id: str | None = None) -> list[dict]:
        """Return agents NOT yet assigned to this context."""
        if not self.agent_service:
            return []

        all_agents = await self.agent_service.list_agents(org_id=org_id)
        assign_repo = ThirdPartyContextAssignmentRepository(self.db)
        mappings = assign_repo.get_assignments_for_context(context_id)
        mapped_ids = {m.agent_id for m in mappings}

        available = []
        for a in all_agents:
            if a["id"] not in mapped_ids:
                available.append({"agent_id": a["id"], "name": a["name"]})

        return available

    async def assign_context(self, context_id: uuid.UUID, agent_id: str) -> dict:
        """Create an assignment and return the updated context."""
        ctx_repo = ThirdPartyContextRepository(self.db)
        ctx = ctx_repo.get(context_id)
        if not ctx:
            raise HTTPException(status_code=404, detail="Context not found")

        assign_repo = ThirdPartyContextAssignmentRepository(self.db)
        assign_repo.assign(context_id, agent_id)

        # Return the ENTIRE context object so the frontend updates immediately
        return await self._enrich_context(ctx)

    def unassign_context(self, context_id: uuid.UUID, agent_id: str) -> None:
        """Remove an assignment."""
        assign_repo = ThirdPartyContextAssignmentRepository(self.db)
        deleted = assign_repo.unassign(context_id, agent_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Assignment not found")

    async def get_complete_contexts_for_agent(self, agent_id: str, org_id: str | None = None) -> list:
        """Return only 'complete' ThirdPartyContext rows assigned to an agent."""
        assign_repo = ThirdPartyContextAssignmentRepository(self.db)
        contexts = assign_repo.get_contexts_for_agent(agent_id, status="complete")
        return [await self._enrich_context(c, org_id=org_id) for c in contexts]
