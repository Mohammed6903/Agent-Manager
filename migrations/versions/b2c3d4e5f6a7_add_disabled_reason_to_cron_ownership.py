"""add disabled_reason to cron_ownership

Adds a nullable ``disabled_reason`` column to ``cron_ownership`` so we
can tell the difference between "user explicitly disabled this cron"
(NULL) and "system auto-disabled this cron because of negative wallet
balance" (``"balance_negative"``). The restore path only re-enables
crons with a non-NULL reason so user-disabled crons are never
accidentally re-enabled.

Revision ID: b2c3d4e5f6a7
Revises: a1f2b3c4d5e6
Create Date: 2026-04-11 14:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f6a7"
down_revision = "a1f2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cron_ownership",
        sa.Column("disabled_reason", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cron_ownership", "disabled_reason")
