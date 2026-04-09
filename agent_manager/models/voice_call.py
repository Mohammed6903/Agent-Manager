"""Voice call persistence models.

A VoiceCall row tracks a single call's lifecycle (outbound-initiated, inbound
deferred for future). VoiceCallTurn rows capture each bot/user utterance so
full transcripts are recoverable after the call ends.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from ..database import Base

VOICE_CALL_STATES = (
    "initiated",     # /calls POST succeeded, waiting for carrier events
    "ringing",       # carrier reports call ringing at callee
    "answered",      # callee picked up, media stream pending/active
    "speaking",      # bot currently speaking
    "listening",     # bot finished speaking, waiting for user speech
    "ended",         # clean termination
    "failed",        # pre-answer failure (carrier rejected, invalid number, etc.)
)

VOICE_CALL_DIRECTIONS = ("outbound", "inbound")

VOICE_CALL_SPEAKERS = ("bot", "user")


class VoiceCall(Base):
    __tablename__ = "voice_calls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telnyx_call_control_id = Column(String, nullable=True, index=True)
    telnyx_call_leg_id = Column(String, nullable=True)

    direction = Column(
        SAEnum(*VOICE_CALL_DIRECTIONS, name="voice_call_direction"),
        nullable=False,
        default="outbound",
    )
    state = Column(
        SAEnum(*VOICE_CALL_STATES, name="voice_call_state"),
        nullable=False,
        default="initiated",
    )

    from_number = Column(String, nullable=False)
    to_number = Column(String, nullable=False)

    # Who (if anyone) owns this call — optional for now.
    user_id = Column(String, nullable=True, index=True)
    agent_id = Column(String, nullable=True, index=True)

    # Free-form context passed in at initiate time (e.g., task briefing).
    initial_message = Column(Text, nullable=True)
    agent_context = Column(JSONB, nullable=True)

    # Outcome metadata.
    end_reason = Column(String, nullable=True)      # hangup-user, hangup-bot, timeout, failed, ...
    failure_error = Column(Text, nullable=True)     # human-readable error if state == failed

    # Lifecycle timestamps.
    started_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    answered_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # Free-form provider metadata (telnyx payloads, cost tracking, etc.).
    meta = Column(JSONB, nullable=False, default=dict)

    turns = relationship(
        "VoiceCallTurn",
        back_populates="call",
        cascade="all, delete-orphan",
        order_by="VoiceCallTurn.turn_index",
    )


class VoiceCallTurn(Base):
    __tablename__ = "voice_call_turns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    call_id = Column(
        UUID(as_uuid=True),
        ForeignKey("voice_calls.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_index = Column(Integer, nullable=False)
    speaker = Column(
        SAEnum(*VOICE_CALL_SPEAKERS, name="voice_call_speaker"),
        nullable=False,
    )
    text = Column(Text, nullable=False)
    started_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    duration_ms = Column(Integer, nullable=True)

    call = relationship("VoiceCall", back_populates="turns")
