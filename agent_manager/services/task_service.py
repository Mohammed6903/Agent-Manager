"""Task management service — CRUD on agent tasks with WebSocket broadcast."""

from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models.agent_task import AgentTask
from ..schemas.task import (
    CreateTaskRequest,
    UpdateTaskRequest,
    TaskResponse,
)
from ..ws_manager import task_ws_manager

logger = logging.getLogger("agent_manager.services.task_service")


def _row_to_response(row: AgentTask) -> TaskResponse:
    """Convert an ORM row to a Pydantic response."""
    return TaskResponse.model_validate(row)


def _row_to_dict(row: AgentTask) -> dict:
    """Convert an ORM row to a plain dict for WS broadcast."""
    return _row_to_response(row).model_dump(mode="json")


class TaskService:
    def __init__(self, db: Session):
        self.db = db

    # ── Create ──────────────────────────────────────────────────────────────────

    async def create_task(self, req: CreateTaskRequest) -> TaskResponse:
        task = AgentTask(
            agent_id=req.agent_id,
            title=req.title,
            description=req.description,
            status=req.status,
            difficulty=req.difficulty,
            sub_tasks=[st.model_dump() for st in req.sub_tasks],
            context_pages=[cp.model_dump() for cp in req.context_pages],
            integrations=req.integrations,
            issues=[iss.model_dump() for iss in req.issues],
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)

        resp = _row_to_response(task)
        await task_ws_manager.broadcast("task_created", _row_to_dict(task))
        logger.info("Task '%s' created for agent '%s'", task.id, task.agent_id)
        return resp

    # ── List ────────────────────────────────────────────────────────────────────

    async def list_tasks(
        self,
        agent_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[TaskResponse]:
        q = self.db.query(AgentTask)
        if agent_id:
            q = q.filter(AgentTask.agent_id == agent_id)
        if status:
            q = q.filter(AgentTask.status == status)
        q = q.order_by(AgentTask.created_at.desc())
        return [_row_to_response(row) for row in q.all()]

    # ── Get ─────────────────────────────────────────────────────────────────────

    async def get_task(self, task_id: UUID) -> TaskResponse:
        task = self.db.query(AgentTask).filter(AgentTask.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")
        return _row_to_response(task)

    # ── Update ──────────────────────────────────────────────────────────────────

    async def update_task(self, task_id: UUID, req: UpdateTaskRequest) -> TaskResponse:
        task = self.db.query(AgentTask).filter(AgentTask.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")

        updates = req.model_dump(exclude_unset=True)
        # Serialize nested Pydantic models to dicts for JSONB
        if "sub_tasks" in updates and updates["sub_tasks"] is not None:
            updates["sub_tasks"] = [st.model_dump() if hasattr(st, "model_dump") else st for st in updates["sub_tasks"]]
        if "context_pages" in updates and updates["context_pages"] is not None:
            updates["context_pages"] = [cp.model_dump() if hasattr(cp, "model_dump") else cp for cp in updates["context_pages"]]
        if "issues" in updates and updates["issues"] is not None:
            updates["issues"] = [iss.model_dump() if hasattr(iss, "model_dump") else iss for iss in updates["issues"]]

        for key, value in updates.items():
            setattr(task, key, value)

        self.db.commit()
        self.db.refresh(task)

        resp = _row_to_response(task)
        await task_ws_manager.broadcast("task_updated", _row_to_dict(task))
        logger.info("Task '%s' updated", task_id)
        return resp

    # ── Delete ──────────────────────────────────────────────────────────────────

    async def delete_task(self, task_id: UUID) -> dict:
        task = self.db.query(AgentTask).filter(AgentTask.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")

        task_data = _row_to_dict(task)
        self.db.delete(task)
        self.db.commit()

        await task_ws_manager.broadcast("task_deleted", task_data)
        logger.info("Task '%s' deleted", task_id)
        return {"status": "deleted", "task_id": str(task_id)}

    # ── Resolve issue ───────────────────────────────────────────────────────────

    async def resolve_issue(self, task_id: UUID, issue_index: int) -> TaskResponse:
        """Mark a specific issue (by index) as resolved."""
        task = self.db.query(AgentTask).filter(AgentTask.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")

        issues = list(task.issues or [])
        if issue_index < 0 or issue_index >= len(issues):
            raise HTTPException(status_code=400, detail=f"Issue index {issue_index} out of range.")

        issues[issue_index]["resolved"] = True
        task.issues = issues
        # Force SQLAlchemy to detect the JSONB mutation
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(task, "issues")

        self.db.commit()
        self.db.refresh(task)

        resp = _row_to_response(task)
        await task_ws_manager.broadcast("issue_resolved", {
            "task_id": str(task_id),
            "issue_index": issue_index,
            "task": _row_to_dict(task),
        })
        logger.info("Issue %d resolved on task '%s'", issue_index, task_id)
        return resp
