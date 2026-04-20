"""Shared progress reporter for all Celery ingest tasks.

`update_progress(state, meta)` updates Celery's result-backend state
(so the SSE polling endpoint at /api/contexts/ram/task/{task_id}/progress
keeps working as a fallback) AND publishes to the Redis pub/sub channel
that FastAPI's task_progress subscriber re-broadcasts via WebSocket.

The progress payload needs `agent_id` so roam-backend's WS bridge can
filter events by the user's accessible agents. Threading agent_id +
task_id through every helper signature down the ingest call stack would
be invasive, so we use contextvars: the Celery task entry point calls
`set_progress_context(agent_id, task_id)` once, and `update_progress`
reads them from the context.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from celery import current_task

from agent_manager.services.task_progress_pubsub import publish_task_progress

_agent_id_var: ContextVar[str | None] = ContextVar("openclaw_progress_agent_id", default=None)
_task_id_var: ContextVar[str | None] = ContextVar("openclaw_progress_task_id", default=None)


def set_progress_context(agent_id: str, task_id: str) -> None:
    """Bind agent_id + task_id for the current Celery task execution.

    Call once at the top of every Celery task that emits progress (via
    update_progress directly or via any helper that does). The
    contextvars persist for the rest of the task's synchronous run.
    """
    _agent_id_var.set(agent_id)
    _task_id_var.set(task_id)


def update_progress(state: str, meta: dict[str, Any]) -> None:
    """Update Celery state and publish a task_progress event.

    Drop-in replacement for the old per-module `_update_progress(state, meta)`.
    If set_progress_context wasn't called (e.g., during tests), only the
    Celery state is updated and the WS publish is skipped.
    """
    current_task.update_state(state=state, meta=meta)
    agent_id = _agent_id_var.get()
    task_id = _task_id_var.get()
    if not agent_id or not task_id:
        return
    payload: dict[str, Any] = {
        **meta,
        "agent_id": agent_id,
        "task_id": task_id,
        "status": state,
    }
    publish_task_progress(payload)
