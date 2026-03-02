"""Cron pipeline repository - stores execution stats and outputs of crons."""

import logging
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from ..models.cron import CronPipelineRun

logger = logging.getLogger("agent_manager.repositories.cron_pipeline")


class CronPipelineRepository:
    """Database-backed cron pipeline run store."""

    def __init__(self, db: Session):
        self.db = db

    def insert_run(self, run_data: dict) -> CronPipelineRun:
        run_id = run_data["id"]
        existing = self.db.query(CronPipelineRun).filter(CronPipelineRun.id == run_id).first()
        if existing:
            for k, v in run_data.items():
                setattr(existing, k, v)
            entry = existing
        else:
            entry = CronPipelineRun(**run_data)
            self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def list_by_cron(self, cron_id: str, limit: int = 20) -> List[dict]:
        runs = (
            self.db.query(CronPipelineRun)
            .filter(CronPipelineRun.cron_id == cron_id)
            .order_by(CronPipelineRun.started_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "status": r.status,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
                "duration_ms": r.duration_ms,
                "tasks": r.tasks,
                "global_integrations": r.global_integrations,
                "global_context_sources": r.global_context_sources,
                "raw_summary": r.raw_summary,
                "summary": r.summary,
                "model": r.model,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in runs
        ]

    def get_latest_summaries(self, cron_ids: List[str]) -> Dict[str, Optional[str]]:
        """Return the summary from the most recent run for each cron_id."""
        if not cron_ids:
            return {}

        from sqlalchemy import distinct
        # Sub-query: latest started_at per cron
        sub = (
            self.db.query(
                CronPipelineRun.cron_id,
                func.max(CronPipelineRun.started_at).label("max_started")
            )
            .filter(CronPipelineRun.cron_id.in_(cron_ids))
            .group_by(CronPipelineRun.cron_id)
            .subquery()
        )
        rows = (
            self.db.query(CronPipelineRun.cron_id, CronPipelineRun.summary)
            .join(sub, (CronPipelineRun.cron_id == sub.c.cron_id)
                       & (CronPipelineRun.started_at == sub.c.max_started))
            .all()
        )
        return {r.cron_id: r.summary for r in rows}

    def aggregate_stats(self, cron_ids: List[str]) -> Dict[str, dict]:
        if not cron_ids:
            return {}
        
        # Calculate total runs and average duration
        stats = (
            self.db.query(
                CronPipelineRun.cron_id,
                func.count(CronPipelineRun.id).label("total_runs"),
                func.avg(CronPipelineRun.duration_ms).label("avg_duration_ms"),
                func.sum(
                    case((CronPipelineRun.status == "success", 1), else_=0)
                ).label("success_count")
            )
            .filter(CronPipelineRun.cron_id.in_(cron_ids))
            .group_by(CronPipelineRun.cron_id)
            .all()
        )
        
        result = {}
        for row in stats:
            total = row.total_runs or 0
            successes = row.success_count or 0
            success_rate = float(successes) / float(total) if total > 0 else 0.0
            
            result[row.cron_id] = {
                "total_runs": total,
                "success_rate": success_rate,
                "avg_duration_ms": float(row.avg_duration_ms) if row.avg_duration_ms else 0.0
            }
            
        return result
