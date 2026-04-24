"""add cache_read_tokens / cache_write_tokens to chat_usage_logs

Openclaw's session JSONL surfaces anthropic prompt-cache counts as
``usage.cacheRead`` and ``usage.cacheWrite``. We were dropping them
on ingest — adding columns so the Savings tab can show them.

Nullable so existing rows keep working; aggregation treats NULL as 0.

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-04-22 14:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "e0f1a2b3c4d5"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_usage_logs",
        sa.Column("cache_read_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "chat_usage_logs",
        sa.Column("cache_write_tokens", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_usage_logs", "cache_write_tokens")
    op.drop_column("chat_usage_logs", "cache_read_tokens")
