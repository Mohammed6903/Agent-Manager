"""add user_id to agent_activities

Adds a nullable ``user_id`` column + index so the activity feed can be
scoped per user. Employees see only rows where ``user_id`` matches them;
founders see all rows (including system-generated rows whose
``user_id`` is NULL).

Existing rows keep ``user_id = NULL`` — they behave like
system-generated activity, visible to founders only. That's the correct
safe default: pre-migration rows didn't track who acted, so we can't
retroactively attribute them to any employee.

Revision ID: c7d8e9f0a1b2
Revises: f3a4e5c6d7b8
Create Date: 2026-04-14 20:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "c7d8e9f0a1b2"
down_revision = "f3a4e5c6d7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_activities",
        sa.Column("user_id", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_agent_activities_user_id",
        "agent_activities",
        ["user_id"],
    )
    op.create_index(
        "ix_agent_activity_agent_user_created",
        "agent_activities",
        ["agent_id", "user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_activity_agent_user_created", table_name="agent_activities")
    op.drop_index("ix_agent_activities_user_id", table_name="agent_activities")
    op.drop_column("agent_activities", "user_id")
