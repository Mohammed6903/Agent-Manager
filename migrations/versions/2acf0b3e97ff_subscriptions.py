"""subscriptions

Revision ID: 2acf0b3e97ff
Revises: 6ec606f03dbb
Create Date: 2026-03-26 10:02:38.760093

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '2acf0b3e97ff'
down_revision: Union[str, Sequence[str], None] = '6ec606f03dbb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create agent_subscriptions and wallet_transactions tables, backfill existing agents."""

    # ── agent_subscriptions ──────────────────────────────────────────────────
    op.create_table(
        "agent_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("amount_cents", sa.Integer(), nullable=False, server_default="2400"),
        sa.Column("next_billing_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_agent_subscriptions_agent_id", "agent_subscriptions", ["agent_id"], unique=True)
    op.create_index("ix_agent_subscriptions_org_id", "agent_subscriptions", ["org_id"])
    op.create_index("ix_agent_subscriptions_user_id", "agent_subscriptions", ["user_id"])
    op.create_index("ix_agent_subscriptions_status", "agent_subscriptions", ["status"])

    # ── wallet_transactions ──────────────────────────────────────────────────
    op.create_table(
        "wallet_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("reference_id", sa.String(), nullable=True),
        sa.Column("balance_after_cents", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_wallet_transactions_user_id", "wallet_transactions", ["user_id"])
    op.create_index("ix_wallet_transactions_agent_id", "wallet_transactions", ["agent_id"])
    op.create_index("ix_wallet_transactions_type", "wallet_transactions", ["type"])

    # ── Backfill: create subscriptions for existing agents ───────────────────
    # Gives existing agents 30 days before their first renewal charge.
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
    op.drop_table("wallet_transactions")
    op.drop_table("agent_subscriptions")
