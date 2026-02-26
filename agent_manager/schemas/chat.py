"""Pydantic request / response models."""

from __future__ import annotations

import re
from typing import Any, List, Optional

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
    # Group chat fields — set room_id for @mention in a group room
    room_id: Optional[str] = None
    recent_context: Optional[str] = None


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


# ── Skills ──────────────────────────────────────────────────────────────────────


class CreateSkillRequest(BaseModel):
    """Create a new skill. `name` becomes the folder slug (kebab-case)."""
    name: str
    content: Optional[str] = None  # If omitted, a default template is used.

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        slug = v.strip().lower().replace(" ", "-")
        if not re.fullmatch(r"[a-z0-9][a-z0-9\-]*", slug):
            raise ValueError("Skill name must be kebab-case (e.g. 'workspace-bridge')")
        return slug


class UpdateSkillRequest(BaseModel):
    """Update the SKILL.md content for an existing skill."""
    content: str


class SkillResponse(BaseModel):
    name: str          # kebab-case slug
    path: str          # absolute path to the SKILL.md file
    status: str        # "created" | "updated" | "deleted" | "ok"


class SkillListResponse(BaseModel):
    skills: List[str]  # list of skill slugs
