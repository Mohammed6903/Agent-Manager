"""merge heads

Revision ID: d36ff18c1178
Revises: 7c2e3d9a1b23, c7d4a42bf03f
Create Date: 2026-03-16 19:53:19.174591

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd36ff18c1178'
down_revision: Union[str, Sequence[str], None] = ('7c2e3d9a1b23', 'c7d4a42bf03f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
