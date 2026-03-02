"""Add api_type to global_integrations

Revision ID: a0105227530c
Revises: 6352f094e06b
Create Date: 2026-03-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a0105227530c'
down_revision: Union[str, Sequence[str], None] = '6352f094e06b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'global_integrations',
        sa.Column('api_type', sa.String(), nullable=False, server_default='rest'),
    )


def downgrade() -> None:
    op.drop_column('global_integrations', 'api_type')
