"""Add summary to cron_pipeline_runs

Revision ID: 6352f094e06b
Revises: 6c86a4f35e58
Create Date: 2026-03-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6352f094e06b'
down_revision: Union[str, Sequence[str], None] = '6c86a4f35e58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cron_pipeline_runs', sa.Column('summary', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('cron_pipeline_runs', 'summary')
