from __future__ import annotations

import importlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..clients.gateway_client import GatewayClient
from ..config import settings
from ..models.chat_usage import ChatUsageLog

logger = logging.getLogger("agent_manager.services.usage_service")


class UsageService:
    def __init__(self, gateway: GatewayClient, db: Session):
        self.gateway = gateway
        self.db = db
        self.state_dir = Path(settings.OPENCLAW_STATE_DIR)

    # ── Log Ingestion ────────────────────────────────────────────────────────────

    async def sync_disk_usage_to_db(self) -> dict[str, int]:
        """Hybrid Index + Detail pipeline for syncing LLM usage and cost data.

        For each agent:
          - Step 1: Stream sessions.json with ``ijson.kvitems`` (no full load).
          - Step 2: Skip sessions whose ``updatedAt`` is not newer than the
            latest ``created_at`` already in the database for that session.
          - Step 3: Parse the corresponding ``.jsonl`` detail file line-by-line,
            filtering for assistant turns only.
          - Step 4: Batch-upsert via PostgreSQL ``ON CONFLICT DO UPDATE``.
        """
        added = 0
        updated = 0
        skipped = 0
        errors = 0

        try:
            module_name = "ijson"
            ijson = importlib.import_module(module_name)
        except ImportError as exc:
            raise RuntimeError(
                "ijson is required for streaming sessions.json. Install it first."
            ) from exc

        try:
            agents = await self.gateway.list_agents()
        except Exception as exc:
            logger.error("Failed to fetch agents from gateway: %s", exc)
            agents = []

        for agent in agents:
            agent_id = agent.get("id")
            if not agent_id:
                continue

            sessions_file = (
                self.state_dir / "agents" / agent_id / "sessions" / "sessions.json"
            )
            if not sessions_file.exists():
                continue

            try:
                a, u, s, e = self._sync_agent(ijson, agent_id, sessions_file)
                added += a
                updated += u
                skipped += s
                errors += e
            except Exception as exc:
                logger.error("Error syncing agent '%s': %s", agent_id, exc)
                errors += 1

        logger.info(
            "Sync complete: added=%s updated=%s skipped=%s errors=%s",
            added,
            updated,
            skipped,
            errors,
        )
        return {"added": added, "updated": updated, "skipped": skipped, "errors": errors}

    def _sync_agent(
        self,
        ijson: Any,
        agent_id: str,
        sessions_file: Path,
    ) -> tuple[int, int, int, int]:
        """Process a single agent's sessions.json end-to-end."""
        total_added = 0
        total_updated = 0
        total_skipped = 0
        total_errors = 0
        sessions_dir = sessions_file.parent

        with open(sessions_file, "rb") as file_obj:
            for session_key, meta in ijson.kvitems(file_obj, ""):
                if not isinstance(meta, dict):
                    continue

                session_id = meta.get("sessionId")
                updated_at_ms = self._parse_updated_at_ms(meta.get("updatedAt"))
                if not session_id or updated_at_ms is None:
                    total_skipped += 1
                    continue

                # Delta guard: compare file's updatedAt against DB max(created_at).
                source_ts = datetime.fromtimestamp(updated_at_ms / 1000, tz=timezone.utc)
                db_max_ts = self._get_session_max_created_at(str(session_id))
                if db_max_ts is not None and source_ts <= db_max_ts:
                    total_skipped += 1
                    continue

                jsonl_file = sessions_dir / f"{session_id}.jsonl"
                if not jsonl_file.exists():
                    total_skipped += 1
                    continue

                user_id = self._extract_user_id_from_session_key(session_key)
                try:
                    records = self._parse_jsonl_session(
                        jsonl_file, str(session_id), agent_id, user_id
                    )
                    if records:
                        a, u = self._upsert_turn_batch(records)
                        total_added += a
                        total_updated += u
                    else:
                        total_skipped += 1
                except Exception as exc:
                    logger.error(
                        "Error processing session '%s' for agent '%s': %s",
                        session_id,
                        agent_id,
                        exc,
                    )
                    total_errors += 1

        return total_added, total_updated, total_skipped, total_errors

    async def sync_single_session(self, agent_id: str, session_key: str, user_id: str) -> None:
        """Sync a single session from disk to the database by looking up its session_id."""
        sessions_file = self.state_dir / "agents" / agent_id / "sessions" / "sessions.json"
        if not sessions_file.exists():
            return
            
        try:
            import ijson
        except ImportError:
            logger.error("ijson is required for streaming sessions.json")
            return

        target_session_id = None
        try:
            with open(sessions_file, "rb") as file_obj:
                for key, meta in ijson.kvitems(file_obj, ""):
                    if key == session_key and isinstance(meta, dict):
                        target_session_id = meta.get("sessionId")
                        break
        except Exception as exc:
            logger.error("Error reading sessions.json for agent %s: %s", agent_id, exc)
            return

        if not target_session_id:
            return

        jsonl_file = self.state_dir / "agents" / agent_id / "sessions" / f"{target_session_id}.jsonl"
        if not jsonl_file.exists():
            return
            
        try:
            records = self._parse_jsonl_session(
                jsonl_file, str(target_session_id), agent_id, user_id
            )
            if records:
                self._upsert_turn_batch(records)
        except Exception as exc:
            logger.error(
                "Error processing single session '%s' for agent '%s': %s",
                target_session_id,
                agent_id,
                exc,
            )

    def _get_session_max_created_at(self, session_id: str) -> datetime | None:
        """Return the latest ``created_at`` stored for a session, or ``None``."""
        result = (
            self.db.query(func.max(ChatUsageLog.created_at))
            .filter(ChatUsageLog.session_id == session_id)
            .scalar()
        )
        if result is None:
            return None
        if isinstance(result, datetime):
            return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
        return None

    def _parse_jsonl_session(
        self,
        jsonl_file: Path,
        session_id: str,
        agent_id: str,
        user_id: str,
    ) -> list[dict[str, Any]]:
        """Read a .jsonl file line-by-line and return assistant-turn records."""
        records: list[dict[str, Any]] = []

        with open(jsonl_file, "r", encoding="utf-8") as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    entry = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                if entry.get("type") != "message":
                    continue

                message = entry.get("message") or {}
                if message.get("role") != "assistant":
                    continue

                message_id = entry.get("id")
                if not message_id:
                    continue

                usage = message.get("usage") or {}
                cost = usage.get("cost") or {}

                records.append(
                    {
                        "id": uuid.uuid4(),
                        "message_id": str(message_id),
                        "user_id": user_id,
                        "session_id": session_id,
                        "agent_id": agent_id,
                        "model": str(message.get("model") or "unknown_model"),
                        "prompt_tokens": int(usage.get("input") or 0),
                        "completion_tokens": int(usage.get("output") or 0),
                        "total_tokens": int(usage.get("totalTokens") or 0),
                        "input_cost": float(cost.get("input") or 0.0) * 2,
                        "output_cost": float(cost.get("output") or 0.0) * 2,
                        "total_cost": float(cost.get("total") or 0.0) * 2,
                        "created_at": (
                            self._parse_iso_timestamp(entry.get("timestamp"))
                            or datetime.now(timezone.utc)
                        ),
                    }
                )

        return records

    def _upsert_turn_batch(
        self, records: list[dict[str, Any]]
    ) -> tuple[int, int]:
        """Batch-upsert turn records via PostgreSQL ``ON CONFLICT DO UPDATE``."""
        stmt = pg_insert(ChatUsageLog).values(records)
        stmt = stmt.on_conflict_do_update(
            index_elements=["message_id"],
            set_={
                "model": stmt.excluded.model,
                "prompt_tokens": stmt.excluded.prompt_tokens,
                "completion_tokens": stmt.excluded.completion_tokens,
                "total_tokens": stmt.excluded.total_tokens,
                "input_cost": stmt.excluded.input_cost,
                "output_cost": stmt.excluded.output_cost,
                "total_cost": stmt.excluded.total_cost,
                "created_at": stmt.excluded.created_at,
            },
        )
        self.db.execute(stmt)
        self.db.commit()
        return len(records), 0

    @staticmethod
    def _parse_updated_at_ms(value: Any) -> int | None:
        """Normalise an ``updatedAt`` value to a millisecond Unix timestamp."""
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            text_value = value.strip()
            if text_value.isdigit():
                return int(text_value)
            if text_value.endswith("Z"):
                text_value = text_value[:-1] + "+00:00"
            try:
                parsed = datetime.fromisoformat(text_value)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return int(parsed.timestamp() * 1000)
        return None

    @staticmethod
    def _parse_iso_timestamp(value: Any) -> datetime | None:
        """Parse an ISO 8601 string or numeric epoch (ms) to a timezone-aware datetime."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        if isinstance(value, str):
            text = value.strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError:
                return None
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        return None

    @staticmethod
    def _extract_user_id_from_session_key(session_key: str) -> str:
        group_match = re.search(r":group:([^:]+)", session_key)
        if group_match:
            return f"group:{group_match.group(1)}"

        parts = session_key.split(":")
        try:
            openai_idx = parts.index("openai-user")
            user_idx = openai_idx + 2
            if len(parts) > user_idx:
                return parts[user_idx]
        except (ValueError, IndexError):
            return "unknown_user"

        return "unknown_user"

    # ── Usage Analytics ──────────────────────────────────────────────────────────

    def get_usage_per_user(self) -> List[Dict[str, Any]]:
        results = (
            self.db.query(
                ChatUsageLog.user_id,
                func.sum(ChatUsageLog.prompt_tokens).label("total_prompt"),
                func.sum(ChatUsageLog.completion_tokens).label("total_completion"),
                func.sum(ChatUsageLog.total_tokens).label("total_tokens"),
                func.count(ChatUsageLog.id).label("total_requests")
            )
            .group_by(ChatUsageLog.user_id)
            .all()
        )
        
        return [
            {
                "user_id": r.user_id,
                "prompt_tokens": r.total_prompt,
                "completion_tokens": r.total_completion,
                "total_tokens": r.total_tokens,
                "total_requests": r.total_requests
            }
            for r in results
        ]

    def get_usage_per_model(self) -> List[Dict[str, Any]]:
        results = (
            self.db.query(
                ChatUsageLog.model,
                func.sum(ChatUsageLog.prompt_tokens).label("total_prompt"),
                func.sum(ChatUsageLog.completion_tokens).label("total_completion"),
                func.sum(ChatUsageLog.total_tokens).label("total_tokens"),
                func.sum(ChatUsageLog.total_cost).label("total_cost")
            )
            .group_by(ChatUsageLog.model)
            .all()
        )
        
        return [
            {
                "model": r.model,
                "prompt_tokens": r.total_prompt,
                "completion_tokens": r.total_completion,
                "total_tokens": r.total_tokens,
                "total_cost": r.total_cost or 0.0
            }
            for r in results
        ]

    def get_current_month_usage(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        
        results = (
            self.db.query(
                ChatUsageLog.model,
                func.sum(ChatUsageLog.total_cost).label("total_cost"),
                func.sum(ChatUsageLog.total_tokens).label("total_tokens")
            )
            .filter(ChatUsageLog.created_at >= start_of_month)
            .group_by(ChatUsageLog.model)
            .all()
        )
        
        models = []
        total_cost = 0.0
        total_tokens = 0
        
        for r in results:
            cost = r.total_cost or 0.0
            models.append({"name": r.model, "cost": cost, "tokens": r.total_tokens or 0})
            total_cost += cost
            total_tokens += (r.total_tokens or 0)
            
        return {
            "total_cost": total_cost,
            "total_tokens": total_tokens,
            "total_models_used": len(models),
            "models": models
        }

    def get_daily_usage_last_7_days(self) -> List[Dict[str, Any]]:
        from sqlalchemy import cast, Date
        from datetime import timedelta
        
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=7)
        
        results = (
            self.db.query(
                cast(ChatUsageLog.created_at, Date).label("date"),
                func.sum(ChatUsageLog.total_cost).label("total_cost"),
                func.sum(ChatUsageLog.total_tokens).label("total_tokens")
            )
            .filter(ChatUsageLog.created_at >= start_date)
            .group_by(cast(ChatUsageLog.created_at, Date))
            .order_by(cast(ChatUsageLog.created_at, Date))
            .all()
        )
        
        return [
            {
                "date": str(r.date),
                "total_cost": r.total_cost or 0.0,
                "total_tokens": r.total_tokens or 0
            }
            for r in results
        ]

    def get_monthly_usage_last_12_months(self) -> List[Dict[str, Any]]:
        from sqlalchemy import extract
        
        now = datetime.now(timezone.utc)
        month = now.month - 11
        year = now.year
        while month <= 0:
            month += 12
            year -= 1
        start_date = datetime(year, month, 1, tzinfo=timezone.utc)
        
        results = (
            self.db.query(
                extract('year', ChatUsageLog.created_at).label("year"),
                extract('month', ChatUsageLog.created_at).label("month"),
                func.sum(ChatUsageLog.total_cost).label("total_cost"),
                func.sum(ChatUsageLog.total_tokens).label("total_tokens")
            )
            .filter(ChatUsageLog.created_at >= start_date)
            .group_by("year", "month")
            .order_by("year", "month")
            .all()
        )
        
        return [
            {
                "month": f"{int(r.year)}-{int(r.month):02d}",
                "total_cost": r.total_cost or 0.0,
                "total_tokens": r.total_tokens or 0
            }
            for r in results
        ]

    async def sync_cron_cost(self, agent_id: str, session_id: str, run_id: str) -> None:
        """Update a CronPipelineRun's costs by reading the corresponding .jsonl session log."""
        import asyncio
        await asyncio.sleep(2)  # Wait for OpenClaw to finish writing to disk

        jsonl_file = self.state_dir / "agents" / agent_id / "sessions" / f"{session_id}.jsonl"
        if not jsonl_file.exists():
            logger.warning("Session log not found for cron sync: %s", jsonl_file)
            return

        total_input_tokens = 0
        total_output_tokens = 0
        total_total_tokens = 0
        total_input_cost = 0.0
        total_output_cost = 0.0
        total_cost = 0.0

        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if entry.get("type") != "message":
                        continue

                    message = entry.get("message") or {}
                    if message.get("role") != "assistant":
                        continue

                    usage = message.get("usage") or {}
                    cost = usage.get("cost") or {}

                    total_input_tokens += int(usage.get("input") or 0)
                    total_output_tokens += int(usage.get("output") or 0)
                    total_total_tokens += int(usage.get("totalTokens") or 0)

                    total_input_cost += float(cost.get("input") or 0.0)
                    total_output_cost += float(cost.get("output") or 0.0)
                    total_cost += float(cost.get("total") or 0.0)

            from ..models.cron import CronPipelineRun
            from ..database import SessionLocal

            # Use a fresh session for background task to ensure it's not closed
            db = SessionLocal()
            try:
                affected = db.query(CronPipelineRun).filter(CronPipelineRun.id == run_id).update({
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "input_cost": total_input_cost * 2,
                    "output_cost": total_output_cost * 2,
                    "total_cost": total_cost * 2
                })
                db.commit()
                if affected == 0:
                    logger.warning("No CronPipelineRun found to update for run_id '%s'", run_id)
                else:
                    logger.info("Synced costs for cron run %s (affected=%s): tokens=%s, total_cost=%s", 
                                run_id, affected, total_total_tokens, total_cost * 2)
            finally:
                db.close()

        except Exception as exc:
            logger.error("Error syncing cron cost for run '%s': %s", run_id, exc)

    def get_token_usage_for_agent(self, agent_id: str, now: datetime) -> Dict[str, Any]:
        """Aggregate token usage for a specific agent from both chat and cron runs."""
        from ..models.cron import CronOwnership, CronPipelineRun

        agent_cron_ids = (
            self.db.query(CronOwnership.cron_id)
            .filter(CronOwnership.agent_id == agent_id)
        )

        # Lifetime totals from Crons
        cron_totals = (
            self.db.query(
                func.coalesce(func.sum(CronPipelineRun.input_tokens), 0).label("inp"),
                func.coalesce(func.sum(CronPipelineRun.output_tokens), 0).label("out"),
                func.count(CronPipelineRun.id).label("cnt"),
            )
            .filter(CronPipelineRun.cron_id.in_(agent_cron_ids))
            .first()
        )

        # Lifetime totals from Chat
        chat_totals = (
            self.db.query(
                func.coalesce(func.sum(ChatUsageLog.prompt_tokens), 0).label("inp"),
                func.coalesce(func.sum(ChatUsageLog.completion_tokens), 0).label("out"),
                func.count(ChatUsageLog.id).label("cnt"),
            )
            .filter(ChatUsageLog.agent_id == agent_id)
            .first()
        )

        input_total = (int(cron_totals.inp) if cron_totals else 0) + (int(chat_totals.inp) if chat_totals else 0)
        output_total = (int(cron_totals.out) if cron_totals else 0) + (int(chat_totals.out) if chat_totals else 0)
        run_count = (int(cron_totals.cnt) if cron_totals else 0) + (int(chat_totals.cnt) if chat_totals else 0)
        total = input_total + output_total

        # This month (Crons)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_start_epoch = int(month_start.timestamp() * 1000)
        
        cron_month_row = (
            self.db.query(
                func.coalesce(
                    func.sum(CronPipelineRun.input_tokens)
                    + func.sum(CronPipelineRun.output_tokens),
                    0,
                )
            )
            .filter(
                CronPipelineRun.cron_id.in_(agent_cron_ids),
                CronPipelineRun.started_at >= month_start_epoch,
            )
            .scalar()
        )
        
        # This month (Chat)
        chat_month_row = (
            self.db.query(
                func.coalesce(
                    func.sum(ChatUsageLog.total_tokens),
                    0,
                )
            )
            .filter(
                ChatUsageLog.agent_id == agent_id,
                ChatUsageLog.created_at >= month_start,
            )
            .scalar()
        )

        this_month = (int(cron_month_row) if cron_month_row else 0) + (int(chat_month_row) if chat_month_row else 0)
        avg_per_task = total // run_count if run_count else 0

        return {
            "total_consumed": total,
            "this_month": this_month,
            "avg_per_task": avg_per_task,
            "breakdown": [
                {"type": "Input", "value": input_total},
                {"type": "Output", "value": output_total},
            ],
        }

    def get_user_chat_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        records = (
            self.db.query(ChatUsageLog)
            .filter(ChatUsageLog.user_id == user_id)
            .order_by(ChatUsageLog.created_at.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "message_id": r.message_id,
                "agent_id": r.agent_id,
                "model": r.model,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "total_tokens": r.total_tokens,
                "timestamp": r.created_at
            }
            for r in records
        ]
