"""add confidence to component_results

Revision ID: add_confidence_component
Revises: update_vector_dimensions_3072
Create Date: 2025-01-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_confidence_component'
down_revision = 'update_vector_dimensions_3072'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    
    # Check if column already exists
    column_check = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = 'component_results' 
            AND column_name = 'confidence'
        )
    """))
    
    if not column_check.scalar():
        # Add confidence column to component_results table
        op.add_column('component_results', sa.Column('confidence', sa.Float(), nullable=True))


def downgrade() -> None:
    # Remove confidence column from component_results table
    op.drop_column('component_results', 'confidence')

