"""add deleted_at to agent_registry

Adds a nullable ``deleted_at`` timestamp to the ``agent_registry`` table
so agent deletion can be a soft-delete at the registry layer instead of
relying on the subscription model (which may or may not have a row
depending on whether ENFORCE_AGENT_SUBSCRIPTION was on when the agent
was created).

Also creates an index on ``deleted_at`` so the common "active agents
only" list query (``WHERE deleted_at IS NULL``) stays fast as the table
grows.

Revision ID: a1f2b3c4d5e6
Revises: d8b2f7c91a3e
Create Date: 2026-04-11 13:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a1f2b3c4d5e6"
down_revision = "d8b2f7c91a3e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_registry",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_agent_registry_deleted_at",
        "agent_registry",
        ["deleted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_registry_deleted_at", table_name="agent_registry")
    op.drop_column("agent_registry", "deleted_at")
