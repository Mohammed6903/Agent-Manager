"""Add request and response transformers to global_integrations

Revision ID: c39b48275da0
Revises: a0105227530c
Create Date: 2026-03-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c39b48275da0'
down_revision: Union[str, Sequence[str], None] = 'a0105227530c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'global_integrations',
        sa.Column('request_transformers', sa.dialects.postgresql.JSONB(), nullable=False, server_default='[]'),
    )
    op.add_column(
        'global_integrations',
        sa.Column('response_transformers', sa.dialects.postgresql.JSONB(), nullable=False, server_default='[]'),
    )


def downgrade() -> None:
    op.drop_column('global_integrations', 'response_transformers')
    op.drop_column('global_integrations', 'request_transformers')
