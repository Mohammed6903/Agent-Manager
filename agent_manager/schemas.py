"""Pydantic request / response models."""

from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, field_validator


# ── Agent CRUD ──────────────────────────────────────────────────────────────────


class CreateAgentRequest(BaseModel):
    agent_id: str
    name: str
    role: str
    soul: Optional[str] = None
    identity: Optional[str] = None

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        if not re.fullmatch(r"[a-z0-9]+", v):
            raise ValueError("agent_id must be lowercase alphanumeric only")
        return v


class UpdateAgentRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    soul: Optional[str] = None
    identity: Optional[str] = None


class AgentResponse(BaseModel):
    agent_id: str
    name: str
    workspace: str
    agent_dir: str
    status: str


# ── Chat ────────────────────────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    agent_id: str
    user_id: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str


# ── Sessions ────────────────────────────────────────────────────────────────────


class NewSessionResponse(BaseModel):
    session_id: str


class SessionClearResponse(BaseModel):
    status: str
    agent_id: str


# ── Health ──────────────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str
    gateway: Any = None
    agents_count: int = 0
    version: str = "1.0.0"
