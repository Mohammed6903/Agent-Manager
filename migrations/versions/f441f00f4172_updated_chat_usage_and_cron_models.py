"""updated chat usage and cron models

Revision ID: f441f00f4172
Revises: 2aefa65b6d94
Create Date: 2026-03-18 16:58:08.320779

"""

from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f441f00f4172"
down_revision: Union[str, Sequence[str], None] = "2aefa65b6d94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "ALTER TABLE chat_usage_logs ADD COLUMN IF NOT EXISTS billed BOOLEAN DEFAULT false NOT NULL"
    )
    op.execute(
        "ALTER TABLE cron_pipeline_runs ADD COLUMN IF NOT EXISTS billed BOOLEAN DEFAULT false NOT NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("cron_pipeline_runs", "billed")
    op.drop_column("chat_usage_logs", "billed")
