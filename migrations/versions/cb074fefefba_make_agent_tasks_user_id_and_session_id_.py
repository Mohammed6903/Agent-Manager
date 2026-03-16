"""make agent_tasks user_id and session_id non-nullable

Revision ID: cb074fefefba
Revises: b78817933c41
Create Date: 2026-03-16 23:08:05.463544

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c91a3f2e5d84'
down_revision: Union[str, Sequence[str], None] = 'b78817933c41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_ID = '69ae817f5adfffd952906d94'


def upgrade() -> None:
    # Fill existing NULLs with the default owner ID
    op.execute(
        sa.text(
            "UPDATE agent_tasks SET user_id = :uid WHERE user_id IS NULL"
        ).bindparams(uid=DEFAULT_ID)
    )
    op.execute(
        sa.text(
            "UPDATE agent_tasks SET session_id = :sid WHERE session_id IS NULL"
        ).bindparams(sid=DEFAULT_ID)
    )

    # Now make them non-nullable
    op.alter_column('agent_tasks', 'user_id',
                    existing_type=sa.String(),
                    nullable=False)
    op.alter_column('agent_tasks', 'session_id',
                    existing_type=sa.String(),
                    nullable=False)


def downgrade() -> None:
    op.alter_column('agent_tasks', 'user_id',
                    existing_type=sa.String(),
                    nullable=True)
    op.alter_column('agent_tasks', 'session_id',
                    existing_type=sa.String(),
                    nullable=True)