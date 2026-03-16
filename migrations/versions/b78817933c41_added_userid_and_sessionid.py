"""added userId and sessionId

Revision ID: b78817933c41
Revises: d36ff18c1178
Create Date: 2026-03-16 22:05:19.660836
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b78817933c41'
down_revision: Union[str, Sequence[str], None] = 'd36ff18c1178'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agent_tasks', sa.Column('user_id', sa.String(), nullable=True))
    op.add_column('agent_tasks', sa.Column('session_id', sa.String(), nullable=True))
    op.create_index(op.f('ix_agent_tasks_session_id'), 'agent_tasks', ['session_id'], unique=False)
    op.create_index(op.f('ix_agent_tasks_user_id'), 'agent_tasks', ['user_id'], unique=False)
    op.execute(sa.text("DROP INDEX IF EXISTS ix_third_party_contexts_creator_user_id"))
    op.drop_column('third_party_contexts', 'creator_user_id')


def downgrade() -> None:
    op.add_column('third_party_contexts', sa.Column('creator_user_id', sa.VARCHAR(), autoincrement=False, nullable=False))
    op.create_index(op.f('ix_third_party_contexts_creator_user_id'), 'third_party_contexts', ['creator_user_id'], unique=False)
    op.drop_index(op.f('ix_agent_tasks_user_id'), table_name='agent_tasks')
    op.drop_index(op.f('ix_agent_tasks_session_id'), table_name='agent_tasks')
    op.drop_column('agent_tasks', 'session_id')
    op.drop_column('agent_tasks', 'user_id')