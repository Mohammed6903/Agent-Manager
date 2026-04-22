"""add cache_read_tokens / cache_write_tokens to cron_pipeline_runs

Mirror of e0f1a2b3c4d5 on the cron side. Cron runs go through the same
openclaw → anthropic cache path as chat turns, but we weren't persisting
the cache token counts. cost.total on cron rows was already correct
(openclaw rolls cache dollars into it); these columns surface the
underlying token volume so the UI breakdown matches.

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5
Create Date: 2026-04-22 14:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "f1a2b3c4d5e6"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cron_pipeline_runs",
        sa.Column("cache_read_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "cron_pipeline_runs",
        sa.Column("cache_write_tokens", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cron_pipeline_runs", "cache_write_tokens")
    op.drop_column("cron_pipeline_runs", "cache_read_tokens")
