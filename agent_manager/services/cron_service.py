"""Cron job management service — wraps OpenClaw gateway cron API + DB ownership."""

import json
import logging
from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..clients.gateway_client import GatewayClient
from ..repositories.cron_ownership_repository import CronOwnershipRepository
from ..repositories.cron_pipeline_repository import CronPipelineRepository
from ..schemas.cron import CreateCronRequest, UpdateCronRequest, CronResponse
from ..config import settings
from ..ws_manager import cron_ws_manager

logger = logging.getLogger("agent_manager.services.cron_service")


class CronService:
    def __init__(self, gateway: GatewayClient, db: Session):
        self.gateway = gateway
        self.ownership = CronOwnershipRepository(db)
        self.pipelines = CronPipelineRepository(db)

    async def create_cron(self, req: CreateCronRequest) -> str:
        """Create a cron job in OpenClaw and store ownership."""
        # Build the OpenClaw job dict
        schedule = {"kind": req.schedule_kind, "expr": req.schedule_expr}
        if req.schedule_kind == "cron" and req.schedule_tz:
            schedule["tz"] = req.schedule_tz
        elif req.schedule_kind == "at":
            schedule = {"kind": "at", "at": req.schedule_expr}
        elif req.schedule_kind == "every":
            schedule = {"kind": "every", "every": req.schedule_expr}

        payload_msg = req.payload_message
        if req.pipeline_template:
            template_json = json.dumps(req.pipeline_template, indent=2)
            payload_msg = f"""{req.payload_message}

        ---
        ## PIPELINE EXECUTION FRAMEWORK

        You are executing a structured scheduled pipeline. Follow all rules exactly.

        ### PIPELINE DEFINITION
        ```json
        {template_json}
        ```

        ### EXECUTION RULES
        1. Execute tasks in the exact order listed. Do not skip or reorder.
        2. Before starting each task, update its status to "running".
        3. Immediately after each task completes successfully, update its status to "success".
        4. If a task fails, set status to "error" and populate the "error" field with a concise description. Then continue to the next task — do not abort the pipeline.
        5. Never add an "error" field to a task that succeeded.
        6. integrations and context_sources on each task reflect what that specific task actually used. They may differ from the template if a task used fewer integrations than planned.
        7. global_integrations and global_context_sources in your final output must be the union of all task integrations and context_sources actually used.

        ### REQUIRED FINAL OUTPUT
        At the very end of your response, after all task execution, output this exact block and nothing after it:

        ```pipeline_result
        {{
        "tasks": [
            {{
            "name": "<task name>",
            "status": "success" | "error",
            "error": "<only if status=error>",
            "integrations": [],
            "context_sources": []
            }}
        ],
        "global_integrations": [],
        "global_context_sources": [],
        "pipeline_status": "success" | "partial" | "error",
        "summary": "<A concise human-readable message for the user summarising any problems, warnings, or noteworthy outcomes from this run. If everything succeeded with no issues, set to null.>"
        }}
        ```

        pipeline_status rules:
        - "success" — all tasks succeeded
        - "partial" — at least one task succeeded and at least one failed
        - "error" — every task failed
        ---"""

        payload = {
            "kind": "agentTurn" if req.session_target == "isolated" else "systemEvent",
            "message": payload_msg
        }

        delivery = {
            "mode": req.delivery_mode,
        }
        if req.delivery_mode == "webhook":
            # Ensure WEBHOOK_BASE_URL is available or use SERVER_URL
            webhook_url = getattr(settings, "WEBHOOK_BASE_URL", settings.SERVER_URL)
            delivery["to"] = f"{webhook_url.rstrip('/')}/api/internal/cron-webhook"

        job = {
            "name": req.name,
            "agentId": req.agent_id,
            "schedule": schedule,
            "sessionTarget": req.session_target,
            "payload": payload,
            "delivery": delivery,
            "enabled": req.enabled,
            "deleteAfterRun": req.delete_after_run
        }

        try:
            result = await self.gateway.cron_add(job)
            # CLI may return "id" or "jobId"
            job_id = result.get("jobId") or result.get("id")
            if not job_id:
                raise HTTPException(status_code=500, detail="Failed to get jobId from OpenClaw")

            # Patch webhook delivery via gateway RPC (CLI cron add has no webhook flag)
            if req.delivery_mode == "webhook":
                webhook_url = getattr(settings, "WEBHOOK_BASE_URL", settings.SERVER_URL)
                await self.gateway.cron_update(job_id, {
                    "delivery": {
                        "mode": "webhook",
                        "to": f"{webhook_url.rstrip('/')}/api/internal/cron-webhook"
                    }
                })

            # Store ownership (sync DB call)
            self.ownership.set(job_id, req.user_id, req.session_id, req.agent_id)

            # Broadcast to WebSocket clients
            await cron_ws_manager.broadcast("cron_created", {
                "job_id": job_id,
                "name": req.name,
                "agent_id": req.agent_id,
                "schedule": schedule,
                "enabled": req.enabled,
                "user_id": req.user_id,
                "session_id": req.session_id,
            })

            return job_id
        except Exception as e:
            logger.error(f"Error creating cron job: {e}")
            raise

    def _extract_state(self, job: dict) -> tuple:
        """Extract last_run_at, next_run_at, last_run_status from CLI output."""
        state = job.get("state", {})
        return (
            state.get("lastRunAtMs") or job.get("lastRunAt"),
            state.get("nextRunAtMs") or job.get("nextRunAt"),
            state.get("lastStatus") or job.get("lastRunStatus"),
        )

    async def list_crons(self, user_id: Optional[str] = None, session_id: Optional[str] = None) -> List[CronResponse]:
        """List and enrich cron jobs from OpenClaw."""
        jobs = await self.gateway.cron_list()
        ownership_map = self.ownership.list_all()
        
        cron_ids = [job.get("id") or job.get("jobId") for job in jobs if (job.get("id") or job.get("jobId"))]
        stats_map = self.pipelines.aggregate_stats(cron_ids)
        summary_map = self.pipelines.get_latest_summaries(cron_ids)

        enriched = []
        for job in jobs:
            # CLI returns "id", not "jobId"
            job_id = job.get("id") or job.get("jobId")
            if not job_id:
                continue

            owner = ownership_map.get(job_id)

            # Filter by ownership if requested
            if user_id:
                if not owner or owner["user_id"] != user_id:
                    continue
            if session_id:
                if not owner or owner["session_id"] != session_id:
                    continue

            last_run_at, next_run_at, last_run_status = self._extract_state(job)
            stats = stats_map.get(job_id, {})
            last_summary = summary_map.get(job_id)

            enriched.append(CronResponse(
                job_id=job_id,
                name=job.get("name", ""),
                agent_id=job.get("agentId", ""),
                schedule=job.get("schedule", {}),
                payload_message=job.get("payload", {}).get("message", ""),
                delivery_mode=job.get("delivery", {}).get("mode", ""),
                enabled=job.get("enabled", True),
                user_id=owner["user_id"] if owner else None,
                session_id=owner["session_id"] if owner else None,
                last_run_at=last_run_at,
                next_run_at=next_run_at,
                last_run_status=last_run_status,
                last_run_summary=last_summary,
                total_runs=stats.get("total_runs"),
                success_rate=stats.get("success_rate"),
                avg_duration_ms=stats.get("avg_duration_ms")
            ))
        return enriched

    async def get_cron(self, job_id: str) -> CronResponse:
        """Get a single enriched cron job."""
        jobs = await self.gateway.cron_list()
        job = next((j for j in jobs if (j.get("id") or j.get("jobId")) == job_id), None)
        if not job:
            raise HTTPException(status_code=404, detail=f"Cron job {job_id} not found in OpenClaw")

        owner = self.ownership.get(job_id)
        last_run_at, next_run_at, last_run_status = self._extract_state(job)
        stats = self.pipelines.aggregate_stats([job_id]).get(job_id, {})
        last_summary = self.pipelines.get_latest_summaries([job_id]).get(job_id)

        return CronResponse(
            job_id=job_id,
            name=job.get("name", ""),
            agent_id=job.get("agentId", ""),
            schedule=job.get("schedule", {}),
            payload_message=job.get("payload", {}).get("message", ""),
            delivery_mode=job.get("delivery", {}).get("mode", ""),
            enabled=job.get("enabled", True),
            user_id=owner["user_id"] if owner else None,
            session_id=owner["session_id"] if owner else None,
            last_run_at=last_run_at,
            next_run_at=next_run_at,
            last_run_status=last_run_status,
            last_run_summary=last_summary,
            total_runs=stats.get("total_runs"),
            success_rate=stats.get("success_rate"),
            avg_duration_ms=stats.get("avg_duration_ms")
        )

    async def update_cron(self, job_id: str, req: UpdateCronRequest) -> dict:
        """Update an existing cron job."""
        updates = {}
        if req.enabled is not None:
            updates["enabled"] = req.enabled
        
        # If any schedule fields are set, we rebuild the schedule object
        if req.schedule_kind or req.schedule_expr:
            schedule = {"kind": req.schedule_kind, "expr": req.schedule_expr}
            if req.schedule_kind == "cron" and req.schedule_tz:
                schedule["tz"] = req.schedule_tz
            updates["schedule"] = schedule

        if req.payload_message:
            updates["payload"] = {"message": req.payload_message}

        result = await self.gateway.cron_edit(job_id, updates)

        # Broadcast update
        await cron_ws_manager.broadcast("cron_updated", {
            "job_id": job_id,
            "updates": updates,
        })

        return result

    async def delete_cron(self, job_id: str):
        """Remove cron job from OpenClaw and delete ownership."""
        await self.gateway.cron_remove(job_id)
        self.ownership.delete(job_id)

        # Broadcast deletion
        await cron_ws_manager.broadcast("cron_deleted", {"job_id": job_id})

    async def trigger_cron(self, job_id: str) -> dict:
        """Run the job immediately."""
        result = await self.gateway.cron_run(job_id)

        # Broadcast trigger
        await cron_ws_manager.broadcast("cron_triggered", {"job_id": job_id})

        return result

    async def get_cron_runs(self, job_id: str, limit: int = 20) -> List[dict]:
        """Get run history — DB first, fall back to gateway."""
        db_runs = self.pipelines.list_by_cron(job_id, limit)
        if db_runs:
            return db_runs
        # Fall back to OpenClaw gateway for jobs not using webhook delivery
        try:
            return await self.gateway.cron_runs(job_id, limit)
        except Exception as e:
            logger.warning(f"Gateway cron_runs fallback failed for {job_id}: {e}")
            return []
