"""Pydantic response schemas for the analytics endpoint."""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel


# ── Tasks ────────────────────────────────────────────────────────────────────────

class DayTasks(BaseModel):
    day: str          # Mon, Tue, …
    tasks: int

class TaskAnalytics(BaseModel):
    completed: int
    pending: int       # assigned + in_progress
    failed: int        # error
    weekly_trend: List[DayTasks]


# ── Jobs (cron) ──────────────────────────────────────────────────────────────────

class JobEntry(BaseModel):
    name: str
    runs: int

class JobAnalytics(BaseModel):
    total_runs: int
    jobs: List[JobEntry]


# ── Work Time ────────────────────────────────────────────────────────────────────

class DayHours(BaseModel):
    day: str
    hours: float

class WorkTimeAnalytics(BaseModel):
    total_hours: float
    this_week: float
    avg_per_day: float
    daily: List[DayHours]


# ── Uptime ───────────────────────────────────────────────────────────────────────

class MonthUptime(BaseModel):
    month: str
    uptime: float

class UptimeAnalytics(BaseModel):
    uptime_percent: float
    downtime_hours: float
    last_downtime: Optional[str] = None
    online: bool
    monthly: List[MonthUptime]


# ── Tokens ───────────────────────────────────────────────────────────────────────

class TokenBreakdown(BaseModel):
    type: str      # "Input" | "Output"
    value: int

class TokenAnalytics(BaseModel):
    total_consumed: int
    this_month: int
    avg_per_task: int
    breakdown: List[TokenBreakdown]


# ── Compute & Storage ────────────────────────────────────────────────────────────

class ComputeAnalytics(BaseModel):
    cpu_usage: float
    memory_used: float      # GB
    memory_total: float     # GB
    storage_used: float     # GB
    storage_total: float    # GB


# ── Interactions ─────────────────────────────────────────────────────────────────

class ContactEntry(BaseModel):
    name: str
    count: int

class InteractionAnalytics(BaseModel):
    total_interactions: int
    unique_people: int
    this_week: int
    top_contacts: List[ContactEntry]


# ── Top-level response ───────────────────────────────────────────────────────────

class AgentAnalyticsResponse(BaseModel):
    agent_id: str
    tasks: TaskAnalytics
    jobs: JobAnalytics
    work_time: WorkTimeAnalytics
    uptime: UptimeAnalytics
    tokens: TokenAnalytics
    compute: ComputeAnalytics
    interactions: InteractionAnalytics
