"""Pydantic schemas for the agent task management system."""

from __future__ import annotations

from typing import Optional, List, Literal
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel


# ── Nested value objects ────────────────────────────────────────────────────────

class SubTask(BaseModel):
    text: str
    done: bool = False


class ContextPage(BaseModel):
    context_name: str
    context_id: str


class TaskIssue(BaseModel):
    description: str
    resolved: bool = False


# ── Request models ──────────────────────────────────────────────────────────────

class CreateTaskRequest(BaseModel):
    agent_id: str
    title: str
    description: Optional[str] = None
    status: Literal["assigned", "in_progress", "completed", "error"] = "assigned"
    difficulty: Literal["low", "medium", "high"] = "medium"
    sub_tasks: List[SubTask] = []
    context_pages: List[ContextPage] = []
    integrations: List[str] = []
    issues: List[TaskIssue] = []


class UpdateTaskRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[Literal["assigned", "in_progress", "completed", "error"]] = None
    difficulty: Optional[Literal["low", "medium", "high"]] = None
    sub_tasks: Optional[List[SubTask]] = None
    context_pages: Optional[List[ContextPage]] = None
    integrations: Optional[List[str]] = None
    issues: Optional[List[TaskIssue]] = None


# ── Response model ──────────────────────────────────────────────────────────────

class TaskResponse(BaseModel):
    id: UUID
    agent_id: str
    title: str
    description: Optional[str] = None
    status: str
    difficulty: str
    sub_tasks: List[SubTask] = []
    context_pages: List[ContextPage] = []
    integrations: List[str] = []
    issues: List[TaskIssue] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
