"""Analytics service — aggregates data from tasks, crons, sessions, and gateway."""

from __future__ import annotations

import json
import logging
import os
import shutil
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import func, case, extract
from sqlalchemy.orm import Session

from ..config import settings
from ..models.agent_task import AgentTask
from ..models.cron import CronOwnership, CronPipelineRun
from ..clients.gateway_client import GatewayClient
from ..repositories.storage import StorageRepository
from ..schemas.analytics import (
    AgentAnalyticsResponse,
    ComputeAnalytics,
    ContactEntry,
    DayHours,
    DayTasks,
    InteractionAnalytics,
    JobAnalytics,
    JobEntry,
    MonthUptime,
    TaskAnalytics,
    TokenAnalytics,
    TokenBreakdown,
    UptimeAnalytics,
    WorkTimeAnalytics,
)

from ..services.usage_service import UsageService

logger = logging.getLogger("agent_manager.services.analytics_service")

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH_ABBR = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


class AnalyticsService:
    def __init__(
        self,
        db: Session,
        gateway: GatewayClient,
        storage: StorageRepository,
        usage_service: Optional[UsageService] = None,
    ):
        self.db = db
        self.gateway = gateway
        self.storage = storage
        self.usage_service = usage_service

    # ── Public entry point ───────────────────────────────────────────────────

    async def get_agent_analytics(self, user_id: str, agent_id: str) -> AgentAnalyticsResponse:
        now = datetime.now(timezone.utc)

        tasks = self._task_analytics(user_id, agent_id, now)
        jobs = await self._job_analytics(user_id, agent_id)
        tokens = self._token_analytics(user_id, agent_id, now)
        work_time = self._work_time_analytics(user_id, agent_id, now)
        uptime = await self._uptime_analytics(user_id, agent_id, now)
        compute = await self._compute_analytics(agent_id)
        interactions = await self._interaction_analytics(agent_id, now)

        return AgentAnalyticsResponse(
            agent_id=agent_id,
            tasks=tasks,
            jobs=jobs,
            work_time=work_time,
            uptime=uptime,
            tokens=tokens,
            compute=compute,
            interactions=interactions,
        )

    # ── Tasks ────────────────────────────────────────────────────────────────

    def _task_analytics(self, user_id: str, agent_id: str, now: datetime) -> TaskAnalytics:
        # Assuming AgentTask has user_id. Let's check the model if possible.
        # If not, we filter by agent_id and assume agent is user-specific.
        # However, the requirement said "fetch results for specific user_id, and agent_id's data".
        query = self.db.query(AgentTask.status, func.count(AgentTask.id)).filter(AgentTask.agent_id == agent_id)
        
        # Check if AgentTask has user_id
        if hasattr(AgentTask, "user_id"):
            query = query.filter(AgentTask.user_id == user_id)

        rows = query.group_by(AgentTask.status).all()
        counts: Dict[str, int] = {r[0]: r[1] for r in rows}
        completed = counts.get("completed", 0)
        pending = counts.get("assigned", 0) + counts.get("in_progress", 0)
        failed = counts.get("error", 0)

        # Weekly trend
        week_start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        trend_query = self.db.query(
                extract("dow", AgentTask.created_at).label("dow"),
                func.count(AgentTask.id),
            ).filter(
                AgentTask.agent_id == agent_id,
                AgentTask.created_at >= week_start,
            )
        
        if hasattr(AgentTask, "user_id"):
            trend_query = trend_query.filter(AgentTask.user_id == user_id)

        week_rows = trend_query.group_by("dow").all()
        dow_map: Dict[int, int] = {int(r[0]): r[1] for r in week_rows}
        weekly_trend = []
        for i, name in enumerate(DAY_NAMES):
            pg_dow = (i + 1) % 7
            weekly_trend.append(DayTasks(day=name, tasks=dow_map.get(pg_dow, 0)))

        return TaskAnalytics(
            completed=completed,
            pending=pending,
            failed=failed,
            weekly_trend=weekly_trend,
        )

    # ── Jobs ─────────────────────────────────────────────────────────────────

    async def _job_analytics(self, user_id: str, agent_id: str) -> JobAnalytics:
        # All cron_ids owned by this agent AND user
        owned_cron_ids = (
            self.db.query(CronOwnership.cron_id)
            .filter(CronOwnership.agent_id == agent_id, CronOwnership.user_id == user_id)
        )

        total_runs_result = (
            self.db.query(func.count(CronPipelineRun.id))
            .filter(CronPipelineRun.cron_id.in_(owned_cron_ids))
            .scalar()
        ) or 0

        # Runs per cron
        per_cron = (
            self.db.query(
                CronPipelineRun.cron_id,
                func.count(CronPipelineRun.id).label("runs"),
            )
            .filter(CronPipelineRun.cron_id.in_(owned_cron_ids))
            .group_by(CronPipelineRun.cron_id)
            .order_by(func.count(CronPipelineRun.id).desc())
            .limit(10)
            .all()
        )

        cron_name_map: Dict[str, str] = {}
        try:
            all_crons = await self.gateway.cron_list()
            cron_name_map = {cron.get("id"): cron.get("name", cron.get("id")) for cron in all_crons}
        except Exception as e:
            logger.warning(f"Failed to fetch cron list from gateway: {e}")

        jobs = [
            JobEntry(name=cron_name_map.get(r.cron_id, r.cron_id[:20]), runs=r.runs) for r in per_cron
        ]

        return JobAnalytics(total_runs=total_runs_result, jobs=jobs)

    # ── Tokens ───────────────────────────────────────────────────────────────

    def _token_analytics(self, user_id: str, agent_id: str, now: datetime) -> TokenAnalytics:
        if self.usage_service:
            usage = self.usage_service.get_token_usage_for_agent(user_id, agent_id, now)
            return TokenAnalytics(
                total_consumed=usage["total_consumed"],
                this_month=usage["this_month"],
                avg_per_task=usage["avg_per_task"],
                breakdown=[
                    TokenBreakdown(type=b["type"], value=b["value"])
                    for b in usage["breakdown"]
                ],
            )

        return TokenAnalytics(
            total_consumed=0,
            this_month=0,
            avg_per_task=0,
            breakdown=[],
        )

    # ── Work Time ────────────────────────────────────────────────────────────

    def _work_time_analytics(self, user_id: str, agent_id: str, now: datetime) -> WorkTimeAnalytics:
        agent_cron_ids = (
            self.db.query(CronOwnership.cron_id)
            .filter(CronOwnership.agent_id == agent_id, CronOwnership.user_id == user_id)
        )

        total_ms = (
            self.db.query(func.coalesce(func.sum(CronPipelineRun.duration_ms), 0))
            .filter(CronPipelineRun.cron_id.in_(agent_cron_ids))
            .scalar()
        ) or 0
        total_hours = round(total_ms / 3_600_000, 1)

        week_start_epoch = int(
            (now - timedelta(days=now.weekday()))
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
            * 1000
        )
        week_ms = (
            self.db.query(func.coalesce(func.sum(CronPipelineRun.duration_ms), 0))
            .filter(
                CronPipelineRun.cron_id.in_(agent_cron_ids),
                CronPipelineRun.started_at >= week_start_epoch,
            )
            .scalar()
        ) or 0
        this_week = round(week_ms / 3_600_000, 1)

        daily: List[DayHours] = []
        for i, name in enumerate(DAY_NAMES):
            day_start = (
                (now - timedelta(days=now.weekday()) + timedelta(days=i))
                .replace(hour=0, minute=0, second=0, microsecond=0)
            )
            day_start_ms = int(day_start.timestamp() * 1000)
            day_end_ms = day_start_ms + 86_400_000

            day_ms = (
                self.db.query(func.coalesce(func.sum(CronPipelineRun.duration_ms), 0))
                .filter(
                    CronPipelineRun.cron_id.in_(agent_cron_ids),
                    CronPipelineRun.started_at >= day_start_ms,
                    CronPipelineRun.started_at < day_end_ms,
                )
                .scalar()
            ) or 0
            daily.append(DayHours(day=name, hours=round(day_ms / 3_600_000, 1)))

        days_active = max(
            1,
            (now - (now - timedelta(days=now.weekday()))).days or 1,
        )
        avg_per_day = round(this_week / days_active, 1) if this_week else 0

        return WorkTimeAnalytics(
            total_hours=total_hours,
            this_week=this_week,
            avg_per_day=avg_per_day,
            daily=daily,
        )

    # ── Uptime ───────────────────────────────────────────────────────────────

    async def _uptime_analytics(
        self, user_id: str, agent_id: str, now: datetime
    ) -> UptimeAnalytics:
        # Check live status
        online = False
        try:
            status = await self.gateway.get_status()
            online = True
        except Exception:
            pass

        agent_cron_ids = (
            self.db.query(CronOwnership.cron_id)
            .filter(CronOwnership.agent_id == agent_id, CronOwnership.user_id == user_id)
        )

        six_months_ago_epoch = int(
            (now - timedelta(days=180))
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
            * 1000
        )

        runs = (
            self.db.query(
                CronPipelineRun.started_at,
                CronPipelineRun.status,
            )
            .filter(
                CronPipelineRun.cron_id.in_(agent_cron_ids),
                CronPipelineRun.started_at >= six_months_ago_epoch,
            )
            .all()
        )

        monthly_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "success": 0})
        last_failure_ts: Optional[int] = None

        for r in runs:
            ts = r.started_at
            if ts:
                dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                month_key = MONTH_ABBR[dt.month - 1]
                monthly_stats[month_key]["total"] += 1
                if r.status == "success":
                    monthly_stats[month_key]["success"] += 1
                else:
                    if last_failure_ts is None or ts > last_failure_ts:
                        last_failure_ts = ts

        monthly: List[MonthUptime] = []
        for i in range(5, -1, -1):
            dt = now - timedelta(days=30 * i)
            key = MONTH_ABBR[dt.month - 1]
            stats = monthly_stats.get(key)
            if stats and stats["total"] > 0:
                pct = round(stats["success"] / stats["total"] * 100, 1)
            else:
                pct = 100.0
            monthly.append(MonthUptime(month=key, uptime=pct))

        total_runs_all = sum(s["total"] for s in monthly_stats.values())
        total_success = sum(s["success"] for s in monthly_stats.values())
        uptime_pct = round(total_success / total_runs_all * 100, 1) if total_runs_all else 100.0
        downtime_hours = round(
            (total_runs_all - total_success) * 0.5, 1
        )

        last_downtime: Optional[str] = None
        if last_failure_ts:
            delta = now - datetime.fromtimestamp(last_failure_ts / 1000, tz=timezone.utc)
            if delta.days > 0:
                last_downtime = f"{delta.days} day{'s' if delta.days != 1 else ''} ago"
            else:
                hours = delta.seconds // 3600
                last_downtime = f"{hours} hour{'s' if hours != 1 else ''} ago"

        return UptimeAnalytics(
            uptime_percent=uptime_pct,
            downtime_hours=downtime_hours,
            last_downtime=last_downtime,
            online=online,
            monthly=monthly,
        )

    # ── Compute & Storage ────────────────────────────────────────────────────

    async def _compute_analytics(self, agent_id: str) -> ComputeAnalytics:
        workspace = str(
            Path(settings.OPENCLAW_STATE_DIR) / f"workspace-{agent_id}"
        )
        agent_dir = str(
            Path(settings.OPENCLAW_STATE_DIR) / "agents" / agent_id
        )

        storage_used_bytes = 0
        for d in (workspace, agent_dir):
            try:
                for dirpath, _dirnames, filenames in os.walk(d):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        if os.path.isfile(fp):
                            storage_used_bytes += os.path.getsize(fp)
            except Exception:
                pass

        storage_used_gb = round(storage_used_bytes / (1024 ** 3), 2)

        # Disk total from the state dir filesystem
        try:
            usage = shutil.disk_usage(settings.OPENCLAW_STATE_DIR)
            storage_total_gb = round(usage.total / (1024 ** 3), 1)
            # System-level memory / CPU (best-effort)
            import psutil
            cpu_usage = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            memory_used_gb = round(mem.used / (1024 ** 3), 1)
            memory_total_gb = round(mem.total / (1024 ** 3), 1)
        except Exception:
            storage_total_gb = 20.0
            cpu_usage = 0
            memory_used_gb = 0
            memory_total_gb = 0

        return ComputeAnalytics(
            cpu_usage=cpu_usage,
            memory_used=memory_used_gb,
            memory_total=memory_total_gb,
            storage_used=storage_used_gb,
            storage_total=storage_total_gb,
        )

    # ── Interactions ─────────────────────────────────────────────────────────

    async def _interaction_analytics(
        self, agent_id: str, now: datetime
    ) -> InteractionAnalytics:
        sessions_file = str(
            Path(settings.OPENCLAW_STATE_DIR)
            / "agents"
            / agent_id
            / "sessions"
            / "sessions.json"
        )
        if not await self.storage.exists(sessions_file):
            return InteractionAnalytics(
                total_interactions=0,
                unique_people=0,
                this_week=0,
                top_contacts=[],
            )

        content = await self.storage.read_text(sessions_file)
        try:
            index: Dict[str, Any] = json.loads(content)
        except json.JSONDecodeError:
            return InteractionAnalytics(
                total_interactions=0,
                unique_people=0,
                this_week=0,
                top_contacts=[],
            )

        contact_counts: Dict[str, int] = defaultdict(int)
        total = 0
        this_week = 0
        week_start_ms = int(
            (now - timedelta(days=now.weekday()))
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
            * 1000
        )

        for session_key, meta in index.items():
            # Extract user identifier from session key
            # Format: agent:<agentId>:openai-user:<agentId>:<userId>[:sessionId]
            #    or:  agent:<agentId>:openai-user:<agentId>:group:<roomId>
            parts = session_key.split(":")
            is_group = ":group:" in session_key

            if is_group:
                # group session — count as interaction with the group
                try:
                    room_idx = parts.index("group")
                    contact_name = f"Group:{parts[room_idx + 1][:8]}"
                except (ValueError, IndexError):
                    contact_name = "Group"
            else:
                # DM session — extract user id
                # typical: agent:X:openai-user:X:userId[:sessionId]
                try:
                    ou_idx = parts.index("openai-user")
                    # userId is two positions after openai-user (agent_id sits in between)
                    contact_name = parts[ou_idx + 2] if len(parts) > ou_idx + 2 else "Unknown"
                except (ValueError, IndexError):
                    contact_name = "Unknown"

            tokens = (meta.get("inputTokens", 0) or 0) + (meta.get("outputTokens", 0) or 0)
            interactions = max(1, tokens // 2000)  # rough: 1 interaction per ~2k tokens
            contact_counts[contact_name] += interactions
            total += interactions

            updated = meta.get("updatedAt")
            if updated and updated >= week_start_ms:
                this_week += interactions

        sorted_contacts = sorted(contact_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        return InteractionAnalytics(
            total_interactions=total,
            unique_people=len(contact_counts),
            this_week=this_week,
            top_contacts=[
                ContactEntry(name=name, count=count)
                for name, count in sorted_contacts
            ],
        )
