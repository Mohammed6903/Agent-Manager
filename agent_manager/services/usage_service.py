from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ..config import settings
from ..models.chat_usage import ChatUsageLog
from ..clients.gateway_client import GatewayClient  # Added GatewayClient

logger = logging.getLogger("agent_manager.services.usage_service")

class UsageService:
    def __init__(self, gateway: GatewayClient, db: Session):
        self.gateway = gateway
        self.db = db
        self.state_dir = Path(settings.OPENCLAW_STATE_DIR)

    # ── Log Ingestion ────────────────────────────────────────────────────────────

    async def sync_disk_usage_to_db(self) -> dict[str, int]:
        """
        Queries the Gateway for active agents, locates their specific session
        directories based on the config, and ingests new token records.
        """
        added_records = 0
        errors = 0

        # 1. Base global sessions (for direct/non-agent LLM calls)
        search_paths = [self.state_dir / "sessions"]

        # 2. Dynamically pull active agents from your OpenClaw config
        try:
            agents = await self.gateway.list_agents()
            for agent in agents:
                agent_dir_str = agent.get("agentDir")
                if agent_dir_str:
                    # In OpenClaw, if agentDir is ".../agents/main/agent", 
                    # the sessions live in ".../agents/main/sessions"
                    session_dir = Path(agent_dir_str).parent / "sessions"
                    search_paths.append(session_dir)
        except Exception as e:
            logger.error(f"Failed to fetch agents from gateway for usage sync: {e}")

        # 3. Process the exact targeted paths
        for session_dir in search_paths:
            if not session_dir.exists() or not session_dir.is_dir():
                continue

            for session_file in session_dir.glob("*.json"):
                try:
                    added, errs = self._process_session_file(session_file)
                    added_records += added
                    errors += errs
                except Exception as e:
                    logger.error(f"Failed to process session file {session_file}: {e}")
                    errors += 1

        self.db.commit()
        logger.info(f"Sync complete. Added {added_records} new usage records. ({errors} errors)")
        return {"added": added_records, "errors": errors}

    def _process_session_file(self, file_path: Path) -> tuple[int, int]:
        added = 0
        errors = 0
        
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                return 0, 1 

        if not isinstance(data, list):
            data = [data]

        for turn in data:
            usage = turn.get("usage", {})
            total_tokens = usage.get("total_tokens", 0)
            
            if total_tokens == 0:
                continue

            message_id = turn.get("id") or turn.get("message_id")
            if not message_id:
                continue 

            log_entry = ChatUsageLog(
                message_id=message_id,
                user_id=turn.get("user", "unknown_user"),
                session_id=turn.get("session_id", file_path.stem),
                agent_id=turn.get("agent_id"),
                model=turn.get("model", "unknown_model"),
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=total_tokens,
                created_at=datetime.now(timezone.utc)
            )

            self.db.add(log_entry)
            try:
                self.db.flush() 
                added += 1
            except IntegrityError:
                self.db.rollback() 
                
        return added, errors

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
                func.sum(ChatUsageLog.total_tokens).label("total_tokens")
            )
            .group_by(ChatUsageLog.model)
            .all()
        )
        
        return [
            {
                "model": r.model,
                "prompt_tokens": r.total_prompt,
                "completion_tokens": r.total_completion,
                "total_tokens": r.total_tokens
            }
            for r in results
        ]

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