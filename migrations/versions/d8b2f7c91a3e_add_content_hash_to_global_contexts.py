"""Add content_hash to global_contexts

Revision ID: d8b2f7c91a3e
Revises: c0d4f1a6e310
Create Date: 2026-04-10 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8b2f7c91a3e'
down_revision: Union[str, Sequence[str], None] = 'c0d4f1a6e310'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — add content_hash column for cheap change detection
    on manual context reindex."""
    op.add_column(
        'global_contexts',
        sa.Column('content_hash', sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('global_contexts', 'content_hash')
