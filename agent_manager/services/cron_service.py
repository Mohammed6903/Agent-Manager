"""Cron job management service — wraps OpenClaw gateway cron API + DB ownership."""

import json
import logging
from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..clients.gateway_client import GatewayClient
from ..repositories.cron_ownership_repository import get_cron_ownership_repository, CronOwnershipRepository
from ..repositories.cron_pipeline_repository import CronPipelineRepository
from ..schemas.cron import CreateCronRequest, UpdateCronRequest, CronResponse
from ..config import settings
from ..ws_manager import cron_ws_manager
from ..database import SessionLocal

logger = logging.getLogger("agent_manager.services.cron_service")


class CronService:
    def __init__(self, gateway: GatewayClient, db: Session):
        self.gateway = gateway
        self.ownership = CronOwnershipRepository(db)
        self.pipelines = CronPipelineRepository(db)

    def _build_schedule(self, kind: str, expr: str, tz: Optional[str] = None) -> dict:
        schedule = {"kind": kind, "expr": expr}
        if kind == "cron" and tz:
            schedule["tz"] = tz
        elif kind == "at":
            schedule = {"kind": "at", "at": expr}
        elif kind == "every":
            schedule = {"kind": "every", "every": expr}
        return schedule

    async def create_cron(self, req: CreateCronRequest) -> dict:
        """Create a new recurring or one-off cron job."""
        if not req.user_id or not req.session_id:
            raise ValueError("user_id and session_id are required")

        payload_msg = req.payload_message

        # If a pipeline template is provided, wrap the prompt to enforce pipeline tracking via API
        if req.pipeline_template and "tasks" in req.pipeline_template:
            tasks_str = json.dumps(req.pipeline_template.get("tasks", []), indent=2)
            payload_msg = f"""{payload_msg}

---
### 🚦 CRON PIPELINE EXECUTION FRAMEWORK

This job requires strict progress tracking. You MUST use the cron-manager skill to manage your execution pipeline.

**PIPELINE TEMPLATE:**
{tasks_str}

### 📋 EXECUTION RULES:
1. **At the very beginning** of your execution, call `POST /api/crons/{req.job_id}/pipeline-runs` with `{{"run_id": "<your-session-id>"}}` to initialize the run. (Extract your session ID from your environment or context).
2. Execute the tasks in the exact order listed.
3. Before starting each task, call `PATCH /api/crons/{req.job_id}/pipeline-runs/<run-id>/tasks/<task-name>` with `{{"status": "running"}}`.
4. After each task completes, call the same PATCH endpoint with `{{"status": "success"}}` (or `"error"` with an `{{"error": "description"}}` payload if it failed).
5. If a task fails, mark it as error but **continue** to the next task if possible.
6. **At the very end** of your execution, call `POST /api/crons/{req.job_id}/pipeline-runs/<run-id>/complete` with a concise `{{"summary": "..."}}` of what was accomplished.

Do NOT output a JSON block at the end. Only use the API endpoints.
---"""

        payload = {
            "kind": "agentTurn" if req.session_target == "isolated" else "systemEvent",
            "message": payload_msg
        }

        delivery = {
            "mode": req.delivery_mode,
        }
        if req.delivery_mode == "webhook":
            webhook_url = getattr(settings, "WEBHOOK_BASE_URL", settings.SERVER_URL)
            delivery["to"] = f"{webhook_url.rstrip('/')}/api/internal/cron-webhook"

        job = {
            "name": req.name,
            "agent_id": req.agent_id,
            "schedule": self._build_schedule(req.schedule_kind, req.schedule_expr, req.schedule_tz),
            "payload": payload,
            "delivery": delivery,
            "enabled": req.enabled,
            "delete_after_run": req.delete_after_run
        }

        result = await self.gateway.cron_create(job)
        job_id = result["job_id"]

        self.ownership.create(
            cron_id=job_id,
            user_id=req.user_id,
            session_id=req.session_id,
            agent_id=req.agent_id
        )

        # Store pipeline template if provided
        if req.pipeline_template or req.schedule_human:
            with SessionLocal() as db:
                repo = get_cron_ownership_repository(db)
                updates = {}
                if req.pipeline_template:
                    updates["pipeline_template"] = req.pipeline_template
                if req.schedule_human:
                    updates["schedule_human"] = req.schedule_human
                repo.update(job_id, **updates)

        # Broadcast creation
        cron_data = await self.get_cron(job_id)
        if cron_data:
            await cron_ws_manager.broadcast("cron_created", {"cron": cron_data.model_dump()})

        return result

    async def init_pipeline_run(self, job_id: str, run_id: str) -> dict:
        import time
        job = await self.get_cron(job_id)
        tasks = []
        if job and job.pipeline_template and job.pipeline_template.get("tasks"):
            for t in job.pipeline_template["tasks"]:
                tasks.append({
                    "name": t.get("name"),
                    "description": t.get("description"),
                    "status": "pending"
                })
        
        run_data = {
            "id": run_id,
            "cron_id": job_id,
            "status": "running",
            "started_at": int(time.time() * 1000),
            "tasks": tasks
        }
        run = self.pipelines.insert_run(run_data)
        
        # Broadcast via websocket
        await cron_ws_manager.broadcast("cron_run_updated", {"job_id": job_id, "run_id": run_id, "updates": {"status": "running", "tasks": tasks}})
        return {"status": "ok", "run_id": run_id}

    async def update_pipeline_task(self, job_id: str, run_id: str, task_name: str, status: str, error: Optional[str] = None) -> dict:
        run = self.pipelines.update_task_status(run_id, task_name, status, error)
        if not run:
            return {"status": "not_found"}
        
        # Broadcast task update
        await cron_ws_manager.broadcast("cron_task_updated", {
            "job_id": job_id, 
            "run_id": run_id, 
            "task": task_name,
            "status": status,
            "error": error
        })
        return {"status": "ok"}

    async def complete_pipeline_run(self, job_id: str, run_id: str, summary: Optional[str] = None, model: Optional[str] = None, usage: Optional[dict] = None) -> dict:
        import time
        updates = {
            "finished_at": int(time.time() * 1000),
            "raw_summary": summary,
            "model": model,
        }
        
        run_old = self.pipelines.get_run(run_id)
        if run_old and run_old.started_at:
            updates["duration_ms"] = updates["finished_at"] - run_old.started_at
            
        if usage:
            if "input_tokens" in usage: updates["input_tokens"] = usage["input_tokens"]
            if "output_tokens" in usage: updates["output_tokens"] = usage["output_tokens"]
            
        run = self.pipelines.complete_run(run_id, updates)
        if not run:
             return {"status": "not_found"}
             
        await cron_ws_manager.broadcast("cron_run_finished", {"job_id": job_id, "run_id": run_id, "status": run.status})
        return {"status": "ok", "pipeline_status": run.status}

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

