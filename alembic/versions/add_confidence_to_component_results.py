"""add confidence to component_results

Revision ID: add_confidence_component
Revises: a44281be1c8f
Create Date: 2025-01-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_confidence_component'
down_revision = 'a44281be1c8f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add confidence column to component_results table
    op.add_column('component_results', sa.Column('confidence', sa.Float(), nullable=True))


def downgrade() -> None:
    # Remove confidence column from component_results table
    op.drop_column('component_results', 'confidence')

