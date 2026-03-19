from __future__ import annotations

import importlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import func, cast, Date, extract
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..clients.gateway_client import GatewayClient
from ..clients.wallet_client import WalletClient, InsufficientBalanceError, DebtLimitReachedError
from ..config import settings
from ..models.chat_usage import ChatUsageLog
from ..models.cron import CronOwnership, CronPipelineRun

logger = logging.getLogger("agent_manager.services.usage_service")


class UsageService:
    def __init__(self, gateway: GatewayClient, db: Session):
        self.gateway = gateway
        self.db = db
        self.state_dir = Path(settings.OPENCLAW_STATE_DIR)

    # ── Log Ingestion ────────────────────────────────────────────────────────────

    async def sync_disk_usage_to_db(self) -> dict[str, int]:
        """Hybrid Index + Detail pipeline for syncing LLM usage and cost data."""
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
            from ..repositories.agent_registry_repository import AgentRegistryRepository
            agents = AgentRegistryRepository(self.db).list()
        except Exception as exc:
            logger.error("Failed to fetch agents from gateway: %s", exc)
            agents = []

        for agent in agents:
            agent_id = agent.agent_id
            if not agent_id:
                continue

            sessions_file = (
                self.state_dir / "agents" / str(agent_id) / "sessions" / "sessions.json"
            )
            if not sessions_file.exists():
                continue

            try:
                a, u, s, e = self._sync_agent(ijson, str(agent_id), sessions_file)
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

        with open(sessions_file, "rb") as file_obj:
            for session_key, meta in ijson.kvitems(file_obj, ""):
                if not isinstance(meta, dict):
                    continue

                # Prefer the explicit sessionFile path written by OpenClaw.
                session_file_path = meta.get("sessionFile")
                if not session_file_path:
                    total_skipped += 1
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

                jsonl_file = Path(session_file_path)
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

        logger.info("Syncing single session for agent %s and session key %s", agent_id, session_key)
            
        try:
            import ijson
        except ImportError:
            logger.error("ijson is required for streaming sessions.json")
            return
        
        target_session_id: str | None = None
        target_session_file: Path | None = None
        try:
            with open(sessions_file, "rb") as file_obj:
                for key, meta in ijson.kvitems(file_obj, ""):
                    if key == session_key and isinstance(meta, dict):
                        target_session_id = str(meta.get("sessionId") or "")
                        session_file = meta.get("sessionFile")
                        if session_file:
                            target_session_file = Path(session_file)
                        logger.info(
                            "Found target session id %s and file %s for agent %s and session key %s",
                            target_session_id,
                            target_session_file,
                            agent_id,
                            session_key,
                        )
                        break
        except Exception as exc:
            logger.error("Error reading sessions.json for agent %s: %s", agent_id, exc)
            return

        if not target_session_file:
            return

        logger.info(
            "Looking for jsonl file: %s (exists: %s)",
            target_session_file,
            target_session_file.exists(),
        )
        if not target_session_file.exists():
            logger.warning("JSONL file not found for session %s", target_session_id)
            return
            
        try:
            records = self._parse_jsonl_session(
                target_session_file, str(target_session_id or ""), agent_id, user_id
            )
            logger.info("Parsed %d records for session %s", len(records) if records else 0, target_session_id)
            if records:
                self._upsert_turn_batch(records)
                logger.info("Upserted %d records for session %s", len(records), target_session_id)
        except Exception as exc:
            logger.error(
                "Error processing single session '%s' for agent '%s': %s",
                target_session_id,
                agent_id,
                exc,
            )

    def _get_org_agent_ids(self, org_id: str) -> set[str] | None:
        """
        Resolve org_id to a set of agent_ids via the registry.
        Returns None if org_id is not provided.
        Returns empty set if org has no agents (caller should return [] immediately).
        """
        if not org_id:
            return None
        from ..repositories.agent_registry_repository import AgentRegistryRepository
        rows = AgentRegistryRepository(self.db).list(org_id=org_id)
        return {r.agent_id for r in rows}

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
                        "input_cost": float(cost.get("input") or 0.0) * settings.COST_MULTIPLIER,
                        "output_cost": float(cost.get("output") or 0.0) * settings.COST_MULTIPLIER,
                        "total_cost": float(cost.get("total") or 0.0) * settings.COST_MULTIPLIER,
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
        try:
            stmt = pg_insert(ChatUsageLog).values(records)
            stmt = stmt.on_conflict_do_update(
                index_elements=["message_id"],
                set_={
                    # Keep attribution consistent even if upstream message_id collides.
                    "user_id": stmt.excluded.user_id,
                    "session_id": stmt.excluded.session_id,
                    "agent_id": stmt.excluded.agent_id,
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
            logger.info("Upserting %d records", len(records))
            self.db.execute(stmt)
            self.db.commit()
            return len(records), 0
        except Exception as e:
            logger.error("Failed to upsert turn batch: %s", e)
            self.db.rollback()
            return 0, len(records)

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

    def get_usage_per_user(self, user_id: str | None = None, agent_id: str | None = None, org_id: str | None = None) -> List[Dict[str, Any]]:
        """Aggregate usage per user, filtering by user_id and agent_id if provided."""
        org_agent_ids = None if agent_id else self._get_org_agent_ids(org_id)
        if org_agent_ids is not None and not org_agent_ids:
            return []
        
        # Chat Usage
        chat_query = self.db.query(
            ChatUsageLog.user_id,
            func.sum(ChatUsageLog.prompt_tokens).label("total_prompt"),
            func.sum(ChatUsageLog.completion_tokens).label("total_completion"),
            func.sum(ChatUsageLog.total_tokens).label("total_tokens"),
            func.sum(ChatUsageLog.total_cost).label("total_cost"),
            func.count(ChatUsageLog.id).label("total_requests")
        )
        if user_id:
            chat_query = chat_query.filter(ChatUsageLog.user_id == user_id)
        if agent_id:
            chat_query = chat_query.filter(ChatUsageLog.agent_id == agent_id)
        elif org_agent_ids is not None:
            chat_query = chat_query.filter(ChatUsageLog.agent_id.in_(org_agent_ids))
        
        chat_results = chat_query.group_by(ChatUsageLog.user_id).all()

        # Cron Usage
        cron_query = self.db.query(
            CronOwnership.user_id,
            func.sum(CronPipelineRun.input_tokens).label("total_prompt"),
            func.sum(CronPipelineRun.output_tokens).label("total_completion"),
            func.sum(CronPipelineRun.input_tokens + CronPipelineRun.output_tokens).label("total_tokens"),
            func.sum(CronPipelineRun.total_cost).label("total_cost"),
            func.count(CronPipelineRun.id).label("total_requests")
        ).join(CronPipelineRun, CronOwnership.cron_id == CronPipelineRun.cron_id)

        if user_id:
            cron_query = cron_query.filter(CronOwnership.user_id == user_id)
        if agent_id:
            cron_query = cron_query.filter(CronOwnership.agent_id == agent_id)
        elif org_agent_ids is not None:
            cron_query = cron_query.filter(CronOwnership.agent_id.in_(org_agent_ids))

        cron_results = cron_query.group_by(CronOwnership.user_id).all()

        # Merge results
        merged: Dict[str, Dict[str, Any]] = {}

        for r in chat_results:
            merged[r.user_id] = {
                "user_id": r.user_id,
                "prompt_tokens": int(r.total_prompt or 0),
                "completion_tokens": int(r.total_completion or 0),
                "total_tokens": int(r.total_tokens or 0),
                "total_cost": float(r.total_cost or 0.0),
                "total_requests": int(r.total_requests or 0)
            }

        for r in cron_results:
            if r.user_id in merged:
                merged[r.user_id]["prompt_tokens"] += int(r.total_prompt or 0)
                merged[r.user_id]["completion_tokens"] += int(r.total_completion or 0)
                merged[r.user_id]["total_tokens"] += int(r.total_tokens or 0)
                merged[r.user_id]["total_cost"] += float(r.total_cost or 0.0)
                merged[r.user_id]["total_requests"] += int(r.total_requests or 0)
            else:
                merged[r.user_id] = {
                    "user_id": r.user_id,
                    "prompt_tokens": int(r.total_prompt or 0),
                    "completion_tokens": int(r.total_completion or 0),
                    "total_tokens": int(r.total_tokens or 0),
                    "total_cost": float(r.total_cost or 0.0),
                    "total_requests": int(r.total_requests or 0)
                }

        return list(merged.values())

    async def get_usage_per_agent_for_user(self, user_id: str, org_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Aggregate usage per agent for a given user, including agent_name."""
        org_agent_ids = self._get_org_agent_ids(org_id)
        if org_agent_ids is not None and not org_agent_ids:
            return []

        # Chat Usage
        chat_query = self.db.query(
            ChatUsageLog.agent_id,
            func.sum(ChatUsageLog.prompt_tokens).label("total_prompt"),
            func.sum(ChatUsageLog.completion_tokens).label("total_completion"),
            func.sum(ChatUsageLog.total_tokens).label("total_tokens"),
            func.sum(ChatUsageLog.total_cost).label("total_cost"),
            func.count(ChatUsageLog.id).label("total_requests")
        ).filter(ChatUsageLog.user_id == user_id, ChatUsageLog.agent_id.isnot(None))

        if org_agent_ids is not None:
            chat_query = chat_query.filter(ChatUsageLog.agent_id.in_(org_agent_ids))

        chat_results = chat_query.group_by(ChatUsageLog.agent_id).all()

        # Cron Usage
        cron_query = self.db.query(
            CronOwnership.agent_id,
            func.sum(CronPipelineRun.input_tokens).label("total_prompt"),
            func.sum(CronPipelineRun.output_tokens).label("total_completion"),
            func.sum(CronPipelineRun.input_tokens + CronPipelineRun.output_tokens).label("total_tokens"),
            func.sum(CronPipelineRun.total_cost).label("total_cost"),
            func.count(CronPipelineRun.id).label("total_requests")
        ).join(CronPipelineRun, CronOwnership.cron_id == CronPipelineRun.cron_id).filter(
            CronOwnership.user_id == user_id, CronOwnership.agent_id.isnot(None)
        )
        if org_agent_ids is not None:
            cron_query = cron_query.filter(CronOwnership.agent_id.in_(org_agent_ids))
        
        cron_results = cron_query.group_by(CronOwnership.agent_id).all()
        
        # Merge results by agent_id
        merged: Dict[str, Dict[str, Any]] = {}

        for r in chat_results:
            a_id = r.agent_id
            merged[a_id] = {
                "agent_id": a_id,
                "prompt_tokens": int(r.total_prompt or 0),
                "completion_tokens": int(r.total_completion or 0),
                "total_tokens": int(r.total_tokens or 0),
                "total_cost": float(r.total_cost or 0.0),
                "total_requests": int(r.total_requests or 0)
            }

        for r in cron_results:
            a_id = r.agent_id
            if a_id in merged:
                merged[a_id]["prompt_tokens"] += int(r.total_prompt or 0)
                merged[a_id]["completion_tokens"] += int(r.total_completion or 0)
                merged[a_id]["total_tokens"] += int(r.total_tokens or 0)
                merged[a_id]["total_cost"] += float(r.total_cost or 0.0)
                merged[a_id]["total_requests"] += int(r.total_requests or 0)
            else:
                merged[a_id] = {
                    "agent_id": a_id,
                    "prompt_tokens": int(r.total_prompt or 0),
                    "completion_tokens": int(r.total_completion or 0),
                    "total_tokens": int(r.total_tokens or 0),
                    "total_cost": float(r.total_cost or 0.0),
                    "total_requests": int(r.total_requests or 0)
                }

        # Fetch agent names from gateway
        agent_name_map: Dict[str, str] = {}
        try:
            from ..repositories.agent_registry_repository import AgentRegistryRepository
            rows = AgentRegistryRepository(self.db).list(org_id=org_id)
            agent_name_map = {r.agent_id: r.name for r in rows}
        except Exception as exc:
            logger.warning("Failed to fetch agents from gateway for usage mapping: %s", exc)

        final_results = []
        for a_id, data in merged.items():
            data["agent_name"] = agent_name_map.get(a_id, a_id)
            final_results.append(data)

        # Sort by cost descending or total tokens
        final_results.sort(key=lambda x: x["total_cost"], reverse=True)
        return final_results

    def get_usage_per_model(self, user_id: str | None = None, agent_id: str | None = None, org_id: str | None = None) -> List[Dict[str, Any]]:
        """Aggregate usage per model, filtering by user_id and agent_id."""
        org_agent_ids = None if agent_id else self._get_org_agent_ids(org_id)
        if org_agent_ids is not None and not org_agent_ids:
            return []
        
        # Chat Usage
        chat_query = self.db.query(
            ChatUsageLog.model,
            func.sum(ChatUsageLog.prompt_tokens).label("total_prompt"),
            func.sum(ChatUsageLog.completion_tokens).label("total_completion"),
            func.sum(ChatUsageLog.total_tokens).label("total_tokens"),
            func.sum(ChatUsageLog.total_cost).label("total_cost")
        )
        if user_id:
            chat_query = chat_query.filter(ChatUsageLog.user_id == user_id)
        if agent_id:
            chat_query = chat_query.filter(ChatUsageLog.agent_id == agent_id)
        elif org_agent_ids is not None:
            chat_query = chat_query.filter(ChatUsageLog.agent_id.in_(org_agent_ids))
        
        chat_results = chat_query.group_by(ChatUsageLog.model).all()

        # Cron Usage
        cron_query = self.db.query(
            CronPipelineRun.model,
            func.sum(CronPipelineRun.input_tokens).label("total_prompt"),
            func.sum(CronPipelineRun.output_tokens).label("total_completion"),
            func.sum(CronPipelineRun.input_tokens + CronPipelineRun.output_tokens).label("total_tokens"),
            func.sum(CronPipelineRun.total_cost).label("total_cost")
        ).join(CronOwnership, CronOwnership.cron_id == CronPipelineRun.cron_id)

        if user_id:
            cron_query = cron_query.filter(CronOwnership.user_id == user_id)
        if agent_id:
            cron_query = cron_query.filter(CronOwnership.agent_id == agent_id)
        elif org_agent_ids is not None:
            cron_query = cron_query.filter(CronOwnership.agent_id.in_(org_agent_ids))


        cron_results = cron_query.group_by(CronPipelineRun.model).all()

        # Merge
        merged: Dict[str, Dict[str, Any]] = {}

        for r in chat_results:
            model = r.model or "unknown"
            merged[model] = {
                "model": model,
                "prompt_tokens": int(r.total_prompt or 0),
                "completion_tokens": int(r.total_completion or 0),
                "total_tokens": int(r.total_tokens or 0),
                "total_cost": float(r.total_cost or 0.0)
            }

        for r in cron_results:
            model = r.model or "unknown"
            if model in merged:
                merged[model]["prompt_tokens"] += int(r.total_prompt or 0)
                merged[model]["completion_tokens"] += int(r.total_completion or 0)
                merged[model]["total_tokens"] += int(r.total_tokens or 0)
                merged[model]["total_cost"] += float(r.total_cost or 0.0)
            else:
                merged[model] = {
                    "model": model,
                    "prompt_tokens": int(r.total_prompt or 0),
                    "completion_tokens": int(r.total_completion or 0),
                    "total_tokens": int(r.total_tokens or 0),
                    "total_cost": float(r.total_cost or 0.0)
                }

        return list(merged.values())

    def get_current_month_usage(self, user_id: str | None = None, agent_id: str | None = None, org_id: str | None = None) -> Dict[str, Any]:
        """Aggregate usage for current month, filtering by user_id and agent_id."""
        now = datetime.now(timezone.utc)
        start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        start_of_month_ms = int(start_of_month.timestamp() * 1000)
        org_agent_ids = None if agent_id else self._get_org_agent_ids(org_id)
        if org_agent_ids is not None and not org_agent_ids:
            return {
                "total_cost": 0.0,
                "total_tokens": 0,
                "total_models_used": 0,
                "models": []
            }
        
        # Chat
        chat_query = self.db.query(
            ChatUsageLog.model,
            func.sum(ChatUsageLog.total_cost).label("total_cost"),
            func.sum(ChatUsageLog.total_tokens).label("total_tokens")
        ).filter(ChatUsageLog.created_at >= start_of_month)

        if user_id:
            chat_query = chat_query.filter(ChatUsageLog.user_id == user_id)
        if agent_id:
            chat_query = chat_query.filter(ChatUsageLog.agent_id == agent_id)
        elif org_agent_ids is not None:
            chat_query = chat_query.filter(ChatUsageLog.agent_id.in_(org_agent_ids))
        
        chat_results = chat_query.group_by(ChatUsageLog.model).all()

        # Cron
        cron_query = self.db.query(
            CronPipelineRun.model,
            func.sum(CronPipelineRun.total_cost).label("total_cost"),
            func.sum(CronPipelineRun.input_tokens + CronPipelineRun.output_tokens).label("total_tokens")
        ).join(CronOwnership, CronOwnership.cron_id == CronPipelineRun.cron_id).filter(CronPipelineRun.started_at >= start_of_month_ms)

        if user_id:
            cron_query = cron_query.filter(CronOwnership.user_id == user_id)
        if agent_id:
            cron_query = cron_query.filter(CronOwnership.agent_id == agent_id)
        elif org_agent_ids is not None:
            cron_query = cron_query.filter(CronOwnership.agent_id.in_(org_agent_ids))

        cron_results = cron_query.group_by(CronPipelineRun.model).all()

        # Merge
        models_data: Dict[str, Dict[str, Any]] = {}
        total_cost = 0.0
        total_tokens = 0

        for r in chat_results:
            name = r.model or "unknown"
            cost = float(r.total_cost or 0.0)
            tokens = int(r.total_tokens or 0)
            models_data[name] = {"name": name, "cost": cost, "tokens": tokens}
            total_cost += cost
            total_tokens += tokens

        for r in cron_results:
            name = r.model or "unknown"
            cost = float(r.total_cost or 0.0)
            tokens = int(r.total_tokens or 0)
            if name in models_data:
                models_data[name]["cost"] += cost
                models_data[name]["tokens"] += tokens
            else:
                models_data[name] = {"name": name, "cost": cost, "tokens": tokens}
            total_cost += cost
            total_tokens += tokens
            
        return {
            "total_cost": total_cost,
            "total_tokens": total_tokens,
            "total_models_used": len(models_data),
            "models": list(models_data.values())
        }

    def get_daily_usage_last_7_days(self, user_id: str | None = None, agent_id: str | None = None, org_id: str | None = None) -> List[Dict[str, Any]]:
        """Aggregate daily usage for last 7 days, filtering by user_id and agent_id."""
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=7)
        start_date_ms = int(start_date.timestamp() * 1000)
        org_agent_ids = None if agent_id else self._get_org_agent_ids(org_id)
        if org_agent_ids is not None and not org_agent_ids:
            return []
        
        # Chat
        chat_query = self.db.query(
            cast(ChatUsageLog.created_at, Date).label("date"),
            func.sum(ChatUsageLog.total_cost).label("total_cost"),
            func.sum(ChatUsageLog.total_tokens).label("total_tokens")
        ).filter(ChatUsageLog.created_at >= start_date)

        if user_id:
            chat_query = chat_query.filter(ChatUsageLog.user_id == user_id)
        if agent_id:
            chat_query = chat_query.filter(ChatUsageLog.agent_id == agent_id)
        elif org_agent_ids is not None:
            chat_query = chat_query.filter(ChatUsageLog.agent_id.in_(org_agent_ids))
        
        chat_results = chat_query.group_by(cast(ChatUsageLog.created_at, Date)).all()

        # Cron
        cron_query = self.db.query(
            cast(func.to_timestamp(CronPipelineRun.started_at / 1000), Date).label("date"),
            func.sum(CronPipelineRun.total_cost).label("total_cost"),
            func.sum(CronPipelineRun.input_tokens + CronPipelineRun.output_tokens).label("total_tokens")
        ).join(CronOwnership, CronOwnership.cron_id == CronPipelineRun.cron_id).filter(CronPipelineRun.started_at >= start_date_ms)

        if user_id:
            cron_query = cron_query.filter(CronOwnership.user_id == user_id)
        if agent_id:
            cron_query = cron_query.filter(CronOwnership.agent_id == agent_id)
        elif org_agent_ids is not None:
            cron_query = cron_query.filter(CronOwnership.agent_id.in_(org_agent_ids))

        cron_results = cron_query.group_by(cast(func.to_timestamp(CronPipelineRun.started_at / 1000), Date)).all()

        # Merge
        merged: Dict[str, Dict[str, Any]] = {}
        
        for r in chat_results:
            d = str(r.date)
            merged[d] = {
                "date": d,
                "total_cost": float(r.total_cost or 0.0),
                "total_tokens": int(r.total_tokens or 0)
            }

        for r in cron_results:
            d = str(r.date)
            if d in merged:
                merged[d]["total_cost"] += float(r.total_cost or 0.0)
                merged[d]["total_tokens"] += int(r.total_tokens or 0)
            else:
                merged[d] = {
                    "date": d,
                    "total_cost": float(r.total_cost or 0.0),
                    "total_tokens": int(r.total_tokens or 0)
                }

        return sorted(list(merged.values()), key=lambda x: x["date"])

    def get_monthly_usage_last_12_months(self, user_id: str | None = None, agent_id: str | None = None, org_id: str | None = None) -> List[Dict[str, Any]]:
        """Aggregate monthly usage for last 12 months, filtering by user_id and agent_id."""
        now = datetime.now(timezone.utc)
        month = now.month - 11
        year = now.year
        while month <= 0:
            month += 12
            year -= 1
        start_date = datetime(year, month, 1, tzinfo=timezone.utc)
        start_date_ms = int(start_date.timestamp() * 1000)

        org_agent_ids = None if agent_id else self._get_org_agent_ids(org_id)
        if org_agent_ids is not None and not org_agent_ids:
            return []
        
        # Chat
        chat_query = self.db.query(
            extract('year', ChatUsageLog.created_at).label("year"),
            extract('month', ChatUsageLog.created_at).label("month"),
            func.sum(ChatUsageLog.total_cost).label("total_cost"),
            func.sum(ChatUsageLog.total_tokens).label("total_tokens")
        ).filter(ChatUsageLog.created_at >= start_date)

        if user_id:
            chat_query = chat_query.filter(ChatUsageLog.user_id == user_id)
        if agent_id:
            chat_query = chat_query.filter(ChatUsageLog.agent_id == agent_id)
        elif org_agent_ids is not None:
            chat_query = chat_query.filter(ChatUsageLog.agent_id.in_(org_agent_ids))
        
        chat_results = chat_query.group_by("year", "month").all()

        # Cron
        cron_query = self.db.query(
            extract('year', func.to_timestamp(CronPipelineRun.started_at / 1000)).label("year"),
            extract('month', func.to_timestamp(CronPipelineRun.started_at / 1000)).label("month"),
            func.sum(CronPipelineRun.total_cost).label("total_cost"),
            func.sum(CronPipelineRun.input_tokens + CronPipelineRun.output_tokens).label("total_tokens")
        ).join(CronOwnership, CronOwnership.cron_id == CronPipelineRun.cron_id).filter(CronPipelineRun.started_at >= start_date_ms)

        if user_id:
            cron_query = cron_query.filter(CronOwnership.user_id == user_id)
        if agent_id:
            cron_query = cron_query.filter(CronOwnership.agent_id == agent_id)
        elif org_agent_ids is not None:
            cron_query = cron_query.filter(CronOwnership.agent_id.in_(org_agent_ids))

        cron_results = cron_query.group_by("year", "month").all()

        # Merge
        merged: Dict[str, Dict[str, Any]] = {}

        for r in chat_results:
            m = f"{int(r.year)}-{int(r.month):02d}"
            merged[m] = {
                "month": m,
                "total_cost": float(r.total_cost or 0.0),
                "total_tokens": int(r.total_tokens or 0)
            }

        for r in cron_results:
            m = f"{int(r.year)}-{int(r.month):02d}"
            if m in merged:
                merged[m]["total_cost"] += float(r.total_cost or 0.0)
                merged[m]["total_tokens"] += int(r.total_tokens or 0)
            else:
                merged[m] = {
                    "month": m,
                    "total_cost": float(r.total_cost or 0.0),
                    "total_tokens": int(r.total_tokens or 0)
                }

        return sorted(list(merged.values()), key=lambda x: x["month"])

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

            from ..database import SessionLocal

            # Use a fresh session for background task to ensure it's not closed
            db = SessionLocal()
            try:
                affected = db.query(CronPipelineRun).filter(CronPipelineRun.id == run_id).update({
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "input_cost": total_input_cost * settings.COST_MULTIPLIER,
                    "output_cost": total_output_cost * settings.COST_MULTIPLIER,
                    "total_cost": total_cost * settings.COST_MULTIPLIER
                })
                db.commit()
                if affected == 0:
                    logger.warning("No CronPipelineRun found to update for run_id '%s'", run_id)
                else:
                    logger.info("Synced costs for cron run %s (affected=%s): tokens=%s, total_cost=%s", 
                                run_id, affected, total_total_tokens, total_cost * settings.COST_MULTIPLIER)
            finally:
                db.close()

        except Exception as exc:
            logger.error("Error syncing cron cost for run '%s': %s", run_id, exc)

    def get_token_usage_for_agent(self, user_id: str, agent_id: str, now: datetime) -> Dict[str, Any]:
        """Aggregate token usage for a specific agent and user from both chat and cron runs."""
        agent_cron_ids = (
            self.db.query(CronOwnership.cron_id)
            .filter(CronOwnership.agent_id == agent_id, CronOwnership.user_id == user_id)
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
            .filter(ChatUsageLog.agent_id == agent_id, ChatUsageLog.user_id == user_id)
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

    async def get_agents_monthly_usage_chart(self, user_id: str, org_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return 12-month token/cost usage grouped by month and agent_id."""
        now = datetime.now(timezone.utc)
        month = now.month - 11
        year = now.year
        while month <= 0:
            month += 12
            year -= 1
        start_date = datetime(year, month, 1, tzinfo=timezone.utc)
        start_date_ms = int(start_date.timestamp() * 1000)

        org_agent_ids = self._get_org_agent_ids(org_id)
        if org_agent_ids is not None and not org_agent_ids:
            return []

        # Chat
        chat_query = self.db.query(
            ChatUsageLog.agent_id,
            extract('year', ChatUsageLog.created_at).label("year"),
            extract('month', ChatUsageLog.created_at).label("month"),
            func.sum(ChatUsageLog.total_cost).label("total_cost"),
            func.sum(ChatUsageLog.total_tokens).label("total_tokens")
        ).filter(ChatUsageLog.created_at >= start_date, ChatUsageLog.user_id == user_id, ChatUsageLog.agent_id.isnot(None))

        if org_agent_ids is not None:
            chat_query = chat_query.filter(ChatUsageLog.agent_id.in_(org_agent_ids))

        chat_results = chat_query.group_by("year", "month", ChatUsageLog.agent_id).all()  # ← moved here

        # Cron
        cron_query = self.db.query(
            CronOwnership.agent_id,
            extract('year', func.to_timestamp(CronPipelineRun.started_at / 1000)).label("year"),
            extract('month', func.to_timestamp(CronPipelineRun.started_at / 1000)).label("month"),
            func.sum(CronPipelineRun.total_cost).label("total_cost"),
            func.sum(CronPipelineRun.input_tokens + CronPipelineRun.output_tokens).label("total_tokens")
        ).join(CronPipelineRun, CronOwnership.cron_id == CronPipelineRun.cron_id)\
        .filter(CronPipelineRun.started_at >= start_date_ms, CronOwnership.user_id == user_id, CronOwnership.agent_id.isnot(None))

        if org_agent_ids is not None:
            cron_query = cron_query.filter(CronOwnership.agent_id.in_(org_agent_ids))

        cron_results = cron_query.group_by("year", "month", CronOwnership.agent_id).all()

        merged: Dict[str, Dict[str, Any]] = {}
        for r in chat_results:
            key = f"{int(r.year)}-{int(r.month):02d}_{r.agent_id}"
            merged[key] = {
                "month": f"{int(r.year)}-{int(r.month):02d}",
                "agent_id": r.agent_id,
                "total_cost": float(r.total_cost or 0.0),
                "total_tokens": int(r.total_tokens or 0)
            }
            
        for r in cron_results:
            key = f"{int(r.year)}-{int(r.month):02d}_{r.agent_id}"
            if key in merged:
                merged[key]["total_cost"] += float(r.total_cost or 0.0)
                merged[key]["total_tokens"] += int(r.total_tokens or 0)
            else:
                merged[key] = {
                    "month": f"{int(r.year)}-{int(r.month):02d}",
                    "agent_id": r.agent_id,
                    "total_cost": float(r.total_cost or 0.0),
                    "total_tokens": int(r.total_tokens or 0)
                }

        agent_name_map = {}
        try:
            from ..repositories.agent_registry_repository import AgentRegistryRepository
            rows = AgentRegistryRepository(self.db).list(org_id=org_id)   # unscoped — all agents
            agent_name_map = {r.agent_id: r.name for r in rows}
        except Exception:
            pass

        final_results = []
        for data in merged.values():
            data["agent_name"] = agent_name_map.get(data["agent_id"], data["agent_id"])
            final_results.append(data)
            
        return sorted(final_results, key=lambda x: x["month"])

    async def get_agents_summary(self, user_id: str, org_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return lifetime and current month summary for all agents of a user."""
        from ..models.agent_task import AgentTask
        now = datetime.now(timezone.utc)
        start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        start_of_month_ms = int(start_of_month.timestamp() * 1000)
        from collections import defaultdict

        org_agent_ids = self._get_org_agent_ids(org_id)
        if org_agent_ids is not None and not org_agent_ids:
            return []

        # 1. Fetch lifetime costs per agent
        lifetime_chat_q = self.db.query(
            ChatUsageLog.agent_id,
            func.sum(ChatUsageLog.total_cost).label("cost")
        ).filter(ChatUsageLog.user_id == user_id, ChatUsageLog.agent_id.isnot(None))
        if org_agent_ids is not None:
            lifetime_chat_q = lifetime_chat_q.filter(ChatUsageLog.agent_id.in_(org_agent_ids))
        lifetime_chat = lifetime_chat_q.group_by(ChatUsageLog.agent_id).all()
        
        lifetime_cron_q = self.db.query(
            CronOwnership.agent_id,
            func.sum(CronPipelineRun.total_cost).label("cost"),
            func.count(CronPipelineRun.id).label("jobs_ran")
        ).join(CronPipelineRun, CronOwnership.cron_id == CronPipelineRun.cron_id)\
         .filter(CronOwnership.user_id == user_id, CronOwnership.agent_id.isnot(None))
        if org_agent_ids is not None:
            lifetime_cron_q = lifetime_cron_q.filter(CronOwnership.agent_id.in_(org_agent_ids))
        lifetime_cron = lifetime_cron_q.group_by(CronOwnership.agent_id).all()

        # 2. Fetch current month metrics per agent
        month_chat_q = self.db.query(
            ChatUsageLog.agent_id,
            func.sum(ChatUsageLog.total_cost).label("cost"),
            func.sum(ChatUsageLog.total_tokens).label("tokens")
        ).filter(
            ChatUsageLog.user_id == user_id,
            ChatUsageLog.agent_id.isnot(None),
            ChatUsageLog.created_at >= start_of_month
        )
        if org_agent_ids is not None:
            month_chat_q = month_chat_q.filter(ChatUsageLog.agent_id.in_(org_agent_ids))
        month_chat = month_chat_q.group_by(ChatUsageLog.agent_id).all()

        month_cron_q = self.db.query(
            CronOwnership.agent_id,
            func.sum(CronPipelineRun.total_cost).label("cost"),
            func.sum(CronPipelineRun.input_tokens + CronPipelineRun.output_tokens).label("tokens")
        ).join(CronPipelineRun, CronOwnership.cron_id == CronPipelineRun.cron_id)\
         .filter(
             CronOwnership.user_id == user_id,
             CronOwnership.agent_id.isnot(None),
             CronPipelineRun.started_at >= start_of_month_ms
         )
        if org_agent_ids is not None:
            month_cron_q = month_cron_q.filter(CronOwnership.agent_id.in_(org_agent_ids))
        month_cron = month_cron_q.group_by(CronOwnership.agent_id).all()

        # 3. Discover agents the user has usage for
        agent_ids = set()
        for r in lifetime_chat: agent_ids.add(r.agent_id)
        for r in lifetime_cron: agent_ids.add(r.agent_id)

        tasks_data = []
        if agent_ids:
            tasks_q = self.db.query(
                AgentTask.agent_id,
                func.count(AgentTask.id).label("tasks_ran")
            ).filter(AgentTask.agent_id.in_(agent_ids))
            tasks_data = tasks_q.group_by(AgentTask.agent_id).all()

        # 4. Top model for current month
        top_chat_q = self.db.query(
            ChatUsageLog.agent_id,
            ChatUsageLog.model,
            func.count(ChatUsageLog.id).label("usage_count")
        ).filter(
            ChatUsageLog.user_id == user_id,
            ChatUsageLog.agent_id.isnot(None),
            ChatUsageLog.created_at >= start_of_month
        )
        if org_agent_ids is not None:
            top_chat_q = top_chat_q.filter(ChatUsageLog.agent_id.in_(org_agent_ids))
        top_models_chat = top_chat_q.group_by(ChatUsageLog.agent_id, ChatUsageLog.model).all()

        top_cron_q = self.db.query(
            CronOwnership.agent_id,
            CronPipelineRun.model,
            func.count(CronPipelineRun.id).label("usage_count")
        ).join(CronPipelineRun, CronOwnership.cron_id == CronPipelineRun.cron_id)\
         .filter(
             CronOwnership.user_id == user_id,
             CronOwnership.agent_id.isnot(None),
             CronPipelineRun.started_at >= start_of_month_ms
         )
        if org_agent_ids is not None:
            top_cron_q = top_cron_q.filter(CronOwnership.agent_id.in_(org_agent_ids))
        top_models_cron = top_cron_q.group_by(CronOwnership.agent_id, CronPipelineRun.model).all()
        
        agent_models = defaultdict(lambda: defaultdict(int))
        for r in top_models_chat: agent_models[r.agent_id][r.model or "unknown"] += r.usage_count
        for r in top_models_cron: agent_models[r.agent_id][r.model or "unknown"] += r.usage_count
        
        top_model_per_agent = {}
        for a_id, models in agent_models.items():
            if models:
                top_model = max(models.items(), key=lambda x: x[1])[0]
                top_model_per_agent[a_id] = top_model

        # Aggregate everything
        agents_summary = {}
        for a_id in agent_ids:
            agents_summary[a_id] = {
                "agent_id": a_id,
                "lifetime_cost": 0.0,
                "current_month_cost": 0.0,
                "current_month_tokens": 0,
                "tasks_ran": 0,
                "jobs_ran": 0,
                "top_model": top_model_per_agent.get(a_id, "unknown")
            }

        for r in lifetime_chat: agents_summary[r.agent_id]["lifetime_cost"] += float(r.cost or 0.0)
        for r in lifetime_cron:
            agents_summary[r.agent_id]["lifetime_cost"] += float(r.cost or 0.0)
            agents_summary[r.agent_id]["jobs_ran"] += int(r.jobs_ran or 0)

        for r in month_chat:
            agents_summary[r.agent_id]["current_month_cost"] += float(r.cost or 0.0)
            agents_summary[r.agent_id]["current_month_tokens"] += int(r.tokens or 0)
        for r in month_cron:
            agents_summary[r.agent_id]["current_month_cost"] += float(r.cost or 0.0)
            agents_summary[r.agent_id]["current_month_tokens"] += int(r.tokens or 0)

        for r in tasks_data:
            if r.agent_id in agents_summary:
                agents_summary[r.agent_id]["tasks_ran"] += int(r.tasks_ran or 0)

        # Get Agent Names
        agent_name_map = {}
        try:
            from ..repositories.agent_registry_repository import AgentRegistryRepository
            rows = AgentRegistryRepository(self.db).list(org_id=org_id)
            agent_name_map = {r.agent_id: r.name for r in rows}
        except Exception:
            pass

        final_results = []
        for a_id, data in agents_summary.items():
            data["agent_name"] = agent_name_map.get(a_id, a_id)
            final_results.append(data)

        final_results.sort(key=lambda x: x["current_month_cost"], reverse=True)
        return final_results

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

    # ── Wallet Deduction ──────────────────────────────────────────────────────

    async def deduct_session_cost(self, user_id: str, session_id: str) -> None:
        """Deduct the total unbilled cost for a chat session from the user's wallet."""
        try:
            unbilled = (
                self.db.query(ChatUsageLog)
                .filter(
                    ChatUsageLog.session_id == session_id,
                    ChatUsageLog.user_id == user_id,
                    ChatUsageLog.billed == False,  # noqa: E712
                )
                .all()
            )

            if not unbilled:
                return

            total_cost = sum(r.total_cost or 0.0 for r in unbilled)
            amount_cents = round(total_cost * 100)
            if amount_cents <= 0:
                return

            turn_count = len(unbilled)
            agent_id = unbilled[0].agent_id or "unknown"
            agent_name = self._resolve_agent_name(agent_id)
            description = (
                f"Agent: {agent_name} — chat "
                f"({turn_count} turn{'s' if turn_count != 1 else ''}, "
                f"${total_cost:.4f})"
            )

            wallet = WalletClient()
            await wallet.deduct_credits(user_id, amount_cents, description)

            # Mark as billed
            for record in unbilled:
                record.billed = True
            self.db.commit()

            logger.info(
                "Deducted %d cents from user %s for session %s",
                amount_cents, user_id, session_id,
            )
        except (InsufficientBalanceError, DebtLimitReachedError) as exc:
            logger.warning(
                "Wallet deduction failed for user %s, session %s: %s",
                user_id, session_id, exc,
            )
        except Exception as exc:
            logger.error("Failed to deduct session cost for %s: %s", session_id, exc)

    async def deduct_cron_run_cost(self, run_id: str, user_id: str) -> None:
        """Deduct the cost of a cron pipeline run from the user's wallet."""
        try:
            run = (
                self.db.query(CronPipelineRun)
                .filter(CronPipelineRun.id == run_id)
                .first()
            )

            if not run or run.billed or not run.total_cost or run.total_cost <= 0:
                return

            amount_cents = round(run.total_cost * 100)
            if amount_cents <= 0:
                return

            # Resolve agent name via cron ownership
            agent_name = run_id
            cron_name = ""
            if run.cron_id:
                ownership = (
                    self.db.query(CronOwnership)
                    .filter(CronOwnership.cron_id == run.cron_id)
                    .first()
                )
                if ownership:
                    agent_name = self._resolve_agent_name(ownership.agent_id)
                    cron_name = run.cron_id

            description = (
                f"Agent: {agent_name} — scheduled task"
                f"{f' ({cron_name})' if cron_name else ''}"
                f" (${run.total_cost:.4f})"
            )

            wallet = WalletClient()
            await wallet.deduct_credits(user_id, amount_cents, description)

            run.billed = True
            self.db.commit()

            logger.info(
                "Deducted %d cents from user %s for cron run %s",
                amount_cents, user_id, run_id,
            )
        except (InsufficientBalanceError, DebtLimitReachedError) as exc:
            logger.warning(
                "Wallet deduction failed for user %s, cron run %s: %s",
                user_id, run_id, exc,
            )
        except Exception as exc:
            logger.error("Failed to deduct cron cost for %s: %s", run_id, exc)

    def _resolve_agent_name(self, agent_id: str) -> str:
        """Look up agent display name from the registry, falling back to agent_id."""
        try:
            from ..repositories.agent_registry_repository import AgentRegistryRepository
            agent = AgentRegistryRepository(self.db).get_by_agent_id(agent_id)
            if agent and agent.name:
                return agent.name
        except Exception:
            pass
        return agent_id
