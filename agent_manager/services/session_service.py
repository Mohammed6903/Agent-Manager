from __future__ import annotations
import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Optional, List

from fastapi import HTTPException
from ..config import settings
from ..repositories.storage import StorageRepository

logger = logging.getLogger("agent_manager.services.session_service")

class SessionService:
    def __init__(self, storage: StorageRepository):
        self.storage = storage

    async def _sessions_index(self, agent_id: str) -> dict:
        sessions_file = str(
            Path(settings.OPENCLAW_STATE_DIR)
            / "agents"
            / agent_id
            / "sessions"
            / "sessions.json"
        )
        if not await self.storage.exists(sessions_file):
            return {}
        content = await self.storage.read_text(sessions_file)
        return json.loads(content)

    async def list_sessions(
        self,
        agent_id: str,
        user_id: Optional[str] = None,
        room_id: Optional[str] = None,
    ) -> Any:
        index = await self._sessions_index(agent_id)

        sessions = []
        for session_key, meta in index.items():
            if room_id:
                if f"openai-user:{agent_id}:group:{room_id}" not in session_key:
                    continue
            elif user_id:
                if f"openai-user:{agent_id}:{user_id}" not in session_key:
                    continue
                if f"openai-user:{agent_id}:group:" in session_key:
                    continue

            is_group = ":group:" in session_key

            sessions.append({
                "session_key": session_key,
                "agent_id": agent_id,
                "session_id": meta.get("sessionId"),
                "session_type": "group" if is_group else "dm",
                "updated_at": meta.get("updatedAt"),
                "input_tokens": meta.get("inputTokens", 0),
                "output_tokens": meta.get("outputTokens", 0),
                "total_tokens": meta.get("totalTokens", 0),
                "model": meta.get("model"),
                "aborted": meta.get("abortedLastRun", False),
            })

        sessions.sort(key=lambda x: x["updated_at"] or 0, reverse=True)

        return {
            "agent_id": agent_id,
            "user_id": user_id,
            "room_id": room_id,
            "sessions": sessions,
            "count": len(sessions),
        }

    async def list_all_sessions(self, user_id: Optional[str] = None) -> Any:
        agents_dir = str(Path(settings.OPENCLAW_STATE_DIR) / "agents")

        if not await self.storage.exists(agents_dir):
            return {"sessions": [], "count": 0}

        all_sessions = []
        agent_ids = await self.storage.list_dirs(agents_dir)

        for agent_id in agent_ids:
            result = await self.list_sessions(agent_id, user_id=user_id)
            all_sessions.extend(result["sessions"])

        all_sessions.sort(key=lambda x: x["updated_at"] or 0, reverse=True)

        return {
            "user_id": user_id,
            "sessions": all_sessions,
            "count": len(all_sessions),
        }

    async def get_session_history(
        self,
        agent_id: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        room_id: Optional[str] = None,
        limit: int = 50,
    ) -> Any:
        index = await self._sessions_index(agent_id)

        if room_id:
            session_key = f"agent:{agent_id}:openai-user:{agent_id}:group:{room_id}"
        elif session_id:
            session_key = f"agent:{agent_id}:openai-user:{agent_id}:{user_id}:{session_id}"
        else:
            session_key = f"agent:{agent_id}:openai-user:{agent_id}:{user_id}"

        session_meta = index.get(session_key)
        if not session_meta:
            return {
                "agent_id": agent_id,
                "user_id": user_id,
                "room_id": room_id,
                "session_key": session_key,
                "messages": [],
                "count": 0,
            }

        transcript_id = session_meta.get("sessionId")
        transcript_file = str(
            Path(settings.OPENCLAW_STATE_DIR)
            / "agents"
            / agent_id
            / "sessions"
            / f"{transcript_id}.jsonl"
        )

        if not await self.storage.exists(transcript_file):
            return {
                "agent_id": agent_id,
                "user_id": user_id,
                "room_id": room_id,
                "session_key": session_key,
                "messages": [],
                "count": 0,
            }

        content = await self.storage.read_text(transcript_file)
        lines = content.strip().splitlines()
        raw_lines = lines[-limit:]

        messages = []
        for line in raw_lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            role = entry.get("message", {}).get("role")
            if role not in ("user", "assistant"):
                continue

            content_text = ""
            raw_content = entry.get("message", {}).get("content", [])

            if isinstance(raw_content, str):
                content_text = raw_content
            elif isinstance(raw_content, list):
                for block in raw_content:
                    if isinstance(block, str):
                        content_text = block
                        break
                    if isinstance(block, dict) and block.get("type") == "text":
                        content_text = block.get("text", "")
                        break

            if content_text:
                messages.append({
                    "role": role,
                    "content": content_text,
                    "timestamp": entry.get("timestamp"),
                })

        return {
            "agent_id": agent_id,
            "user_id": user_id,
            "room_id": room_id,
            "session_key": session_key,
            "messages": messages,
            "count": len(messages),
        }

    async def clear_agent_memory(self, agent_id: str) -> dict[str, str]:
        memory_path = str(
            Path(settings.OPENCLAW_STATE_DIR)
            / f"workspace-{agent_id}"
            / "MEMORY.md"
        )
        workspace_path = str(Path(settings.OPENCLAW_STATE_DIR) / f"workspace-{agent_id}")

        if not await self.storage.exists(workspace_path):
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "workspace_not_found",
                    "message": f"Workspace for agent '{agent_id}' not found",
                },
            )

        await self.storage.write_text(memory_path, "")
        logger.info("Cleared MEMORY.md for agent '%s'", agent_id)
        return {"status": "cleared", "agent_id": agent_id}
