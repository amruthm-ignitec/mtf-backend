"""merge extraction tables and donor approvals

Revision ID: a44281be1c8f
Revises: a1b2c3d4e5f6, add_donor_approvals
Create Date: 2025-11-26 17:58:03.216706

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a44281be1c8f'
down_revision = ('a1b2c3d4e5f6', 'add_donor_approvals')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass


