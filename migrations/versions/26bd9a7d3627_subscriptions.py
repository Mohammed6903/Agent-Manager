"""subscriptions

Revision ID: 26bd9a7d3627
Revises: 8d57bd5bb24a
Create Date: 2026-03-26 15:54:46.168100

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect


# revision identifiers, used by Alembic.
revision: str = '26bd9a7d3627'
down_revision: Union[str, Sequence[str], None] = '8d57bd5bb24a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    conn = op.get_bind()
    return name in sa_inspect(conn).get_table_names()


def upgrade() -> None:
    """Create agent_subscriptions and wallet_transactions tables if they don't exist,
    then backfill existing agents with active subscriptions."""

    if not _table_exists("agent_subscriptions"):
        op.create_table('agent_subscriptions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('agent_id', sa.String(), nullable=False),
        sa.Column('org_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('next_billing_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_agent_subscriptions_agent_id'), 'agent_subscriptions', ['agent_id'], unique=True)
        op.create_index(op.f('ix_agent_subscriptions_org_id'), 'agent_subscriptions', ['org_id'], unique=False)
        op.create_index(op.f('ix_agent_subscriptions_status'), 'agent_subscriptions', ['status'], unique=False)
        op.create_index(op.f('ix_agent_subscriptions_user_id'), 'agent_subscriptions', ['user_id'], unique=False)

    if not _table_exists("wallet_transactions"):
        op.create_table('wallet_transactions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('agent_id', sa.String(), nullable=True),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('reference_id', sa.String(), nullable=True),
        sa.Column('balance_after_cents', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_wallet_transactions_agent_id'), 'wallet_transactions', ['agent_id'], unique=False)
        op.create_index(op.f('ix_wallet_transactions_type'), 'wallet_transactions', ['type'], unique=False)
        op.create_index(op.f('ix_wallet_transactions_user_id'), 'wallet_transactions', ['user_id'], unique=False)

    # Backfill: create subscriptions for existing agents that don't have one yet
    if _table_exists("agent_registry"):
        op.execute(
            """
            INSERT INTO agent_subscriptions (id, agent_id, org_id, user_id, status, amount_cents, next_billing_date, created_at, updated_at)
            SELECT
                gen_random_uuid(),
                ar.agent_id,
                COALESCE(ar.org_id, ''),
                COALESCE(ar.user_id, ''),
                'active',
                2400,
                NOW() + INTERVAL '30 days',
                NOW(),
                NOW()
            FROM agent_registry ar
            WHERE NOT EXISTS (
                SELECT 1 FROM agent_subscriptions sub WHERE sub.agent_id = ar.agent_id
            )
            """
        )


def downgrade() -> None:
    """Drop agent_subscriptions and wallet_transactions tables."""
    if _table_exists("wallet_transactions"):
        op.drop_table('wallet_transactions')
    if _table_exists("agent_subscriptions"):
        op.drop_table('agent_subscriptions')
