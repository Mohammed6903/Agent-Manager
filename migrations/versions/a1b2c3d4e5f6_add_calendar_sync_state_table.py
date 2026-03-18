"""replace gmail_sync_state + calendar_sync_state with unified integration_sync_state

Revision ID: a1b2c3d4e5f6
Revises: f441f00f4172
Create Date: 2026-03-18 18:00:00.000000

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f441f00f4172"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create the unified table
    op.create_table(
        "integration_sync_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("integration_name", sa.String(), nullable=False),
        sa.Column("sync_cursor", sa.String(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_fetched", sa.Integer(), server_default="0", nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "integration_name", name="uq_agent_integration_sync"),
    )
    op.create_index(
        op.f("ix_integration_sync_state_agent_id"),
        "integration_sync_state",
        ["agent_id"],
    )

    # 2. Migrate existing gmail_sync_state data
    op.execute("""
        INSERT INTO integration_sync_state (agent_id, integration_name, sync_cursor, last_synced_at, total_fetched, created_at, updated_at)
        SELECT agent_id, 'gmail', history_id, last_synced_at, total_fetched, created_at, updated_at
        FROM gmail_sync_state
    """)

    # 3. Drop old tables
    op.drop_table("gmail_sync_state")


def downgrade() -> None:
    # Recreate gmail_sync_state
    op.create_table(
        "gmail_sync_state",
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("history_id", sa.String(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_fetched", sa.Integer(), server_default="0", nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("agent_id"),
    )
    op.create_index(op.f("ix_gmail_sync_state_agent_id"), "gmail_sync_state", ["agent_id"])

    # Migrate data back
    op.execute("""
        INSERT INTO gmail_sync_state (agent_id, history_id, last_synced_at, total_fetched, created_at, updated_at)
        SELECT agent_id, sync_cursor, last_synced_at, total_fetched, created_at, updated_at
        FROM integration_sync_state
        WHERE integration_name = 'gmail'
    """)

    # Drop unified table
    op.drop_index(op.f("ix_integration_sync_state_agent_id"), table_name="integration_sync_state")
    op.drop_table("integration_sync_state")
