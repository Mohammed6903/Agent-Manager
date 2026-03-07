"""add integration_metadata to agent_integrations

Revision ID: f3a2c1b4d5e6
Revises: 04fae5bcfee0
Create Date: 2026-03-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'f3a2c1b4d5e6'
down_revision = '04fae5bcfee0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'agent_integrations',
        sa.Column('integration_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('agent_integrations', 'integration_metadata')
