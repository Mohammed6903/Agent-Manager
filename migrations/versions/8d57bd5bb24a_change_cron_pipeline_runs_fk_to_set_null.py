"""change cron_pipeline_runs FK from CASCADE to SET NULL

Preserves pipeline run history (analytics/billing data) when cron
ownership records are deleted during agent removal.

Revision ID: 8d57bd5bb24a
Revises: 2acf0b3e97ff
Create Date: 2026-03-26 11:45:51.692906

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8d57bd5bb24a'
down_revision: Union[str, Sequence[str], None] = '2acf0b3e97ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Change cron_pipeline_runs.cron_id FK from CASCADE to SET NULL."""
    op.alter_column('cron_pipeline_runs', 'cron_id', nullable=True)
    op.drop_constraint('cron_pipeline_runs_cron_id_fkey', 'cron_pipeline_runs', type_='foreignkey')
    op.create_foreign_key(
        'cron_pipeline_runs_cron_id_fkey',
        'cron_pipeline_runs', 'cron_ownership',
        ['cron_id'], ['cron_id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    """Revert to CASCADE delete."""
    op.drop_constraint('cron_pipeline_runs_cron_id_fkey', 'cron_pipeline_runs', type_='foreignkey')
    op.create_foreign_key(
        'cron_pipeline_runs_cron_id_fkey',
        'cron_pipeline_runs', 'cron_ownership',
        ['cron_id'], ['cron_id'],
        ondelete='CASCADE',
    )
    op.alter_column('cron_pipeline_runs', 'cron_id', nullable=False)
