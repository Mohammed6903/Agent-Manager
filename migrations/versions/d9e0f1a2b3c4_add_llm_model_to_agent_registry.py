"""add llm_model to agent_registry

Adds a nullable ``llm_model`` column so the user's provider choice
(OpenAI vs Anthropic, mapped to a concrete model string) is stored
on the agent row at create time and routed via the ``x-openclaw-model``
header at chat time.

Nullable: existing rows keep NULL and fall back to the gateway default.

Revision ID: d9e0f1a2b3c4
Revises: c7d8e9f0a1b2
Create Date: 2026-04-22 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "d9e0f1a2b3c4"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_registry",
        sa.Column("llm_model", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_registry", "llm_model")
