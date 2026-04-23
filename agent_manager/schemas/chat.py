"""Pydantic request / response models."""

from __future__ import annotations

import re
from typing import Any, List, Optional

from pydantic import BaseModel, field_validator


# ── Agent CRUD ──────────────────────────────────────────────────────────────────


# Allowed values for ``agent_type`` on create/update. Mirrors the
# module-level constants in ``agent_manager.models.agent_registry`` but
# we keep them as a literal set here to avoid a schemas → models import
# cycle. If you add a new type, update both places.
_ALLOWED_AGENT_TYPES = ("default", "qa", "voice")

# Allowed values for ``llm_model`` on create AND for the per-request
# ``ChatRequest.model`` override. Mirrors ``ALLOWED_LLM_MODELS`` in
# agent_manager.models.agent_registry; kept literal here to avoid the
# import cycle. Update both when adding providers.
_ALLOWED_LLM_MODELS = (
    "openai/gpt-5.1",
    "openai/gpt-4.1",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "anthropic/claude-opus-4-5",
    "anthropic/claude-sonnet-4-5",
    "anthropic/claude-haiku-4-5",
)


class CreateAgentRequest(BaseModel):
    agent_id: str
    name: str
    role: Optional[str] = None
    soul: Optional[str] = None
    identity: Optional[str] = None
    org_id: str | None = None
    user_id: str | None = None

    # Agent type + Q&A-specific configuration. All optional on create —
    # ``agent_type`` defaults to "default" if omitted, preserving the
    # historical behavior for any client that doesn't know about the
    # new field yet. The four ``qa_*`` fields are only meaningful when
    # ``agent_type == "qa"`` but we don't reject them on other types
    # (so founders can flip an agent between types later without
    # losing their Q&A config).
    agent_type: Optional[str] = None
    qa_welcome_message: Optional[str] = None
    qa_persona_instructions: Optional[str] = None
    qa_page_title: Optional[str] = None
    qa_page_subtitle: Optional[str] = None

    # Per-agent LLM model. Sent to the openclaw gateway via the
    # ``x-openclaw-model`` header on every chat call for this agent.
    # Locked at create time: UpdateAgentRequest intentionally omits it.
    llm_model: Optional[str] = None

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        if not re.fullmatch(r"[a-z0-9]+", v):
            raise ValueError("agent_id must be lowercase alphanumeric only")
        return v

    @field_validator("agent_type")
    @classmethod
    def validate_agent_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if v not in _ALLOWED_AGENT_TYPES:
            raise ValueError(
                f"agent_type must be one of {_ALLOWED_AGENT_TYPES}, got {v!r}"
            )
        return v

    @field_validator("llm_model")
    @classmethod
    def validate_llm_model(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if v not in _ALLOWED_LLM_MODELS:
            raise ValueError(
                f"llm_model must be one of {_ALLOWED_LLM_MODELS}, got {v!r}"
            )
        return v


class UpdateAgentRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    soul: Optional[str] = None
    identity: Optional[str] = None
    # Q&A-related fields are also updatable so founders can tune their
    # Q&A agent's persona / welcome / branding without deleting and
    # recreating the agent. Same validation rules as CreateAgentRequest.
    agent_type: Optional[str] = None
    qa_welcome_message: Optional[str] = None
    qa_persona_instructions: Optional[str] = None
    qa_page_title: Optional[str] = None
    qa_page_subtitle: Optional[str] = None

    @field_validator("agent_type")
    @classmethod
    def validate_agent_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if v not in _ALLOWED_AGENT_TYPES:
            raise ValueError(
                f"agent_type must be one of {_ALLOWED_AGENT_TYPES}, got {v!r}"
            )
        return v


class AgentResponse(BaseModel):
    agent_id: str
    name: str
    workspace: str
    agent_dir: str
    status: str
    org_id: str | None = None
    user_id: str | None = None
    # New metadata surfaced so the frontend can render the type badge
    # and the Q&A config editor. All optional for backward compat.
    agent_type: Optional[str] = None
    qa_welcome_message: Optional[str] = None
    qa_persona_instructions: Optional[str] = None
    qa_page_title: Optional[str] = None
    qa_page_subtitle: Optional[str] = None
    llm_model: Optional[str] = None


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
    # Per-turn LLM model override. When omitted, the agent's locked
    # default (``agent_registry.llm_model``) is used; when both are
    # absent the gateway falls back to its configured primary. Must
    # be one of ``_ALLOWED_LLM_MODELS``.
    model: Optional[str] = None

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if v not in _ALLOWED_LLM_MODELS:
            raise ValueError(
                f"model must be one of {_ALLOWED_LLM_MODELS}, got {v!r}"
            )
        return v


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


