"""add voice_call tables

Revision ID: c0d4f1a6e310
Revises: 558c75046bb6
Create Date: 2026-04-09 14:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "c0d4f1a6e310"
down_revision: Union[str, Sequence[str], None] = "558c75046bb6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


VOICE_CALL_STATES = (
    "initiated",
    "ringing",
    "answered",
    "speaking",
    "listening",
    "ended",
    "failed",
)

VOICE_CALL_DIRECTIONS = ("outbound", "inbound")

VOICE_CALL_SPEAKERS = ("bot", "user")


def upgrade() -> None:
    # NOTE: Enums created inline via the column definition below; no CREATE TYPE needed.

    op.create_table(
        "voice_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("telnyx_call_control_id", sa.String(), nullable=True),
        sa.Column("telnyx_call_leg_id", sa.String(), nullable=True),
        sa.Column(
            "direction",
            sa.Enum(*VOICE_CALL_DIRECTIONS, name="voice_call_direction"),
            nullable=False,
            server_default="outbound",
        ),
        sa.Column(
            "state",
            sa.Enum(*VOICE_CALL_STATES, name="voice_call_state"),
            nullable=False,
            server_default="initiated",
        ),
        sa.Column("from_number", sa.String(), nullable=False),
        sa.Column("to_number", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("agent_id", sa.String(), nullable=True),
        sa.Column("initial_message", sa.Text(), nullable=True),
        sa.Column("agent_context", postgresql.JSONB(), nullable=True),
        sa.Column("end_reason", sa.String(), nullable=True),
        sa.Column("failure_error", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "meta",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(
        "ix_voice_calls_telnyx_call_control_id",
        "voice_calls",
        ["telnyx_call_control_id"],
    )
    op.create_index("ix_voice_calls_user_id", "voice_calls", ["user_id"])
    op.create_index("ix_voice_calls_agent_id", "voice_calls", ["agent_id"])

    op.create_table(
        "voice_call_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "call_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("voice_calls.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column(
            "speaker",
            sa.Enum(*VOICE_CALL_SPEAKERS, name="voice_call_speaker"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
    )
    op.create_index("ix_voice_call_turns_call_id", "voice_call_turns", ["call_id"])


def downgrade() -> None:
    op.drop_index("ix_voice_call_turns_call_id", table_name="voice_call_turns")
    op.drop_table("voice_call_turns")
    op.drop_index("ix_voice_calls_agent_id", table_name="voice_calls")
    op.drop_index("ix_voice_calls_user_id", table_name="voice_calls")
    op.drop_index(
        "ix_voice_calls_telnyx_call_control_id", table_name="voice_calls"
    )
    op.drop_table("voice_calls")
    sa.Enum(name="voice_call_speaker").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="voice_call_state").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="voice_call_direction").drop(op.get_bind(), checkfirst=True)
