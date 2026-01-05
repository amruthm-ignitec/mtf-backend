"""merge_migration_heads

Revision ID: merge_heads
Revises: ('95630ab9fe0f', 'update_vector_dimensions_3072')
Create Date: 2026-01-05 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'merge_heads'
down_revision = ('95630ab9fe0f', 'update_vector_dimensions_3072')
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Merge migration to combine two separate migration branches.
    This is a no-op migration that just merges the branches.
    """
    pass


def downgrade() -> None:
    pass

