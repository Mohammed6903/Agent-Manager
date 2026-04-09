"""Pydantic schemas for voice-call HTTP endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class InitiateCallRequest(BaseModel):
    to: str = Field(
        ..., description="Destination phone number in E.164 format, e.g. '+918689908731'"
    )
    agent_id: str = Field(
        ...,
        description="OpenClaw agent id that will handle the conversation",
    )
    initial_message: Optional[str] = Field(
        default=None,
        description="Greeting the bot speaks when the callee answers. Defaults to a generic hello if omitted.",
    )
    system_prompt: Optional[str] = Field(
        default=None,
        description="Optional system prompt prepended to the voice agent's conversation. Useful for scoping the call to a specific task.",
    )
    agent_context: Optional[dict[str, Any]] = Field(
        default=None,
        description="Arbitrary JSON passed through to persistence for future use (e.g., task briefings).",
    )
    user_id: Optional[str] = Field(
        default=None, description="Owner user id (for listing/filtering)."
    )


class InitiateCallResponse(BaseModel):
    call_id: str
    telnyx_call_control_id: Optional[str]
    state: str
    from_number: str
    to_number: str
    started_at: datetime
    # Idempotency signaling. ``deduped=True`` means we found an existing
    # active call to the same number for this agent and returned its info
    # WITHOUT placing a new call. ``message`` is a human/LLM-readable
    # one-liner the agent can echo back to the user — designed to make it
    # crystal clear to the agent that the operation succeeded so it does
    # not retry the make_phone_call tool.
    deduped: bool = False
    message: str = "Call placed successfully and is being delivered to the recipient."


class TurnView(BaseModel):
    turn_index: int
    speaker: str
    text: str
    started_at: datetime


class CallView(BaseModel):
    id: str
    direction: str
    state: str
    from_number: str
    to_number: str
    user_id: Optional[str]
    agent_id: Optional[str]
    initial_message: Optional[str]
    end_reason: Optional[str]
    failure_error: Optional[str]
    started_at: datetime
    answered_at: Optional[datetime]
    ended_at: Optional[datetime]
    duration_ms: Optional[int]
    turns: list[TurnView] = Field(default_factory=list)
