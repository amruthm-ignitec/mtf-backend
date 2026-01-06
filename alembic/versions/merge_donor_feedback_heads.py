"""merge_donor_feedback_heads

Revision ID: merge_donor_feedback_heads
Revises: ('4ef89e83816b', 'add_donor_feedback')
Create Date: 2026-01-XX XX:XX:XX.XXXXXX

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'merge_donor_feedback_heads'
down_revision = ('4ef89e83816b', 'add_donor_feedback')
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

