"""Service layer for ThirdPartyContext creation and management."""
from __future__ import annotations

import logging
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..celery_app import celery_app
from ..repositories.integration_repository import IntegrationRepository
from ..repositories.third_party_context_repository import ThirdPartyContextRepository
from ..repositories.third_party_context_assignment_repository import (
    ThirdPartyContextAssignmentRepository,
)
from ..services import gmail_service

logger = logging.getLogger(__name__)


class ThirdPartyContextService:
    """Orchestrates validation and task dispatch for third-party context jobs."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_gmail_context(self, agent_id: str, force_full_sync: bool = False) -> dict:
        """Validate credentials, create a tracking row, and enqueue the sync task.

        Args:
            agent_id: The agent requesting Gmail sync.
            force_full_sync: When True, clear any stored sync checkpoint so the
                task performs a full re-sync instead of an incremental one.

        Returns:
            Dict with task_id, context_id, and a status message.

        Raises:
            HTTPException 400: If Gmail is not assigned or credentials are invalid.
        """
        ctx_repo = ThirdPartyContextRepository(self.db)

        # Reject duplicate starts while another Gmail run is active.
        active_ctx = ctx_repo.get_active_by_agent_and_integration(agent_id, "gmail")
        if active_ctx:
            if active_ctx.celery_task_id:
                task_state = celery_app.AsyncResult(active_ctx.celery_task_id).state
                if task_state in {"SUCCESS", "FAILURE", "FAILED", "REVOKED"}:
                    ctx_repo.update_status(active_ctx.id, "failed")
                else:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "A Gmail context task is already running for this "
                            f"agent. task_id={active_ctx.celery_task_id}"
                        ),
                    )
            else:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "A Gmail context task is already running for this "
                        "agent. Please wait for it to complete."
                    ),
                )

        # Verify Gmail is assigned to this agent
        assignment = IntegrationRepository(self.db).get_assignment(agent_id, "gmail")
        if not assignment:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Gmail integration is not assigned to agent '{agent_id}'. "
                    "Please connect Gmail first."
                ),
            )

        # Verify Gmail credentials are still valid
        svc = gmail_service.get_service(self.db, agent_id)
        if not svc:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Gmail credentials are invalid or expired. "
                    "Please reconnect Gmail."
                ),
            )

        # Create the tracking row in pending state
        ctx = ctx_repo.create(
            agent_id=agent_id,
            integration_name="gmail",
            metadata=assignment.integration_metadata,
        )

        # Enqueue the merged task — import here to avoid circular imports at module load
        from ..tasks.gmail_context_task import ingest_and_pipeline_gmail  # noqa: PLC0415

        task = ingest_and_pipeline_gmail.delay(agent_id, str(ctx.id), force_full_sync)

        # Attach the task ID to the row now that we have it
        ctx_repo.update_task(ctx.id, task.id, "ingesting")

        logger.info(
            "Gmail context task %s enqueued for agent %s (context %s).",
            task.id,
            agent_id,
            ctx.id,
        )
        return {
            "task_id": task.id,
            "context_id": str(ctx.id),
            "message": "Background Gmail sync started.",
        }

    def purge_gmail_context_data(self, context_id: uuid.UUID) -> dict:
        """Enqueue background deletion of all Gmail data for this context.

        Marks the context as 'deleting', dispatches a Celery task that removes
        S3 objects, Qdrant points, and the DB row, then returns the task_id so
        callers can poll for progress.

        Args:
            context_id: ID of the ThirdPartyContext row to purge.

        Returns:
            Dict with task_id, context_id, agent_id, and a status message.

        Raises:
            HTTPException 404: If the context does not exist.
            HTTPException 400: If the context is not a Gmail context.
        """
        ctx_repo = ThirdPartyContextRepository(self.db)
        context = ctx_repo.get(context_id)
        if not context:
            raise HTTPException(status_code=404, detail="Context not found")

        if context.integration_name != "gmail":
            raise HTTPException(
                status_code=400,
                detail="Data purge is currently supported only for Gmail contexts.",
            )

        from ..tasks.gmail_context_task import delete_gmail_context  # noqa: PLC0415

        task = delete_gmail_context.delay(context.agent_id, str(context_id))

        ctx_repo.update_task(context_id, task.id, "deleting")

        logger.info(
            "Delete task %s enqueued for agent %s (context %s).",
            task.id,
            context.agent_id,
            context_id,
        )
        return {
            "task_id": task.id,
            "context_id": str(context_id),
            "agent_id": context.agent_id,
            "integration": context.integration_name,
            "message": "Background delete started.",
        }

    # ── List / Get ───────────────────────────────────────────────────────────

    def get_context(self, context_id: uuid.UUID) -> dict:
        """Fetch a single ThirdPartyContext by ID."""
        ctx_repo = ThirdPartyContextRepository(self.db)
        ctx = ctx_repo.get(context_id)
        if not ctx:
            raise HTTPException(status_code=404, detail="Context not found")
        return ctx

    def list_contexts_for_agent(self, agent_id: str) -> list:
        """Return all ThirdPartyContext rows assigned to an agent."""
        assign_repo = ThirdPartyContextAssignmentRepository(self.db)
        return assign_repo.get_contexts_for_agent(agent_id)

    # ── Assignment ───────────────────────────────────────────────────────────

    def assign_context(self, context_id: uuid.UUID, agent_id: str) -> dict:
        """Create an assignment between an agent and a ThirdPartyContext."""
        ctx_repo = ThirdPartyContextRepository(self.db)
        ctx = ctx_repo.get(context_id)
        if not ctx:
            raise HTTPException(status_code=404, detail="Context not found")

        assign_repo = ThirdPartyContextAssignmentRepository(self.db)
        row = assign_repo.assign(context_id, agent_id)
        return row

    def unassign_context(self, context_id: uuid.UUID, agent_id: str) -> None:
        """Remove an assignment between an agent and a ThirdPartyContext."""
        assign_repo = ThirdPartyContextAssignmentRepository(self.db)
        deleted = assign_repo.unassign(context_id, agent_id)
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail="Assignment not found",
            )

    def get_all_complete_contexts(self) -> list:
        """Return all ThirdPartyContext rows whose status is 'complete'."""
        ctx_repo = ThirdPartyContextRepository(self.db)
        return ctx_repo.get_all_complete()

    def get_complete_contexts_for_agent(self, agent_id: str) -> list:
        """Return only 'complete' ThirdPartyContext rows assigned to an agent."""
        assign_repo = ThirdPartyContextAssignmentRepository(self.db)
        return assign_repo.get_contexts_for_agent(agent_id, status="complete")
