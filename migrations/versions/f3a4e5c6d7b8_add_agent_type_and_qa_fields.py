"""Add agent_type and Q&A config fields

Revision ID: f3a4e5c6d7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-11 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a4e5c6d7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ``agent_type`` and four Q&A config columns to ``agent_registry``.

    ``agent_type`` is the core enum driving agent behavior: Default (the
    historical full-featured chat agent), Q&A (public-facing answer-only
    assistant reachable by unauthenticated visitors), and Voice (label
    only in this phase, voice-specific behavior deferred).

    The ``server_default`` on ``agent_type`` makes the migration safe for
    existing rows — every current agent gets ``"default"`` automatically
    so zero existing behavior changes on migration apply. The four Q&A
    columns are all nullable and only populated when a founder creates
    a Q&A agent with those fields.
    """
    op.add_column(
        "agent_registry",
        sa.Column(
            "agent_type",
            sa.String(),
            nullable=False,
            server_default="default",
        ),
    )
    op.add_column(
        "agent_registry",
        sa.Column("qa_welcome_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "agent_registry",
        sa.Column("qa_persona_instructions", sa.Text(), nullable=True),
    )
    op.add_column(
        "agent_registry",
        sa.Column("qa_page_title", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "agent_registry",
        sa.Column("qa_page_subtitle", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    """Reverse the upgrade."""
    op.drop_column("agent_registry", "qa_page_subtitle")
    op.drop_column("agent_registry", "qa_page_title")
    op.drop_column("agent_registry", "qa_persona_instructions")
    op.drop_column("agent_registry", "qa_welcome_message")
    op.drop_column("agent_registry", "agent_type")
