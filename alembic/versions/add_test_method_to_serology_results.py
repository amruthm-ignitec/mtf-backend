"""Add test_method column to serology_results

Revision ID: add_test_method_serology
Revises: 
Create Date: 2025-12-02 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_test_method_serology'
down_revision = 'add_confidence_component'  # Latest migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add test_method column to serology_results table
    # Check if column exists first (idempotent)
    conn = op.get_bind()
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = 'serology_results' 
            AND column_name = 'test_method'
        )
    """))
    
    if not result.scalar():
        op.add_column('serology_results', sa.Column('test_method', sa.String(), nullable=True))


def downgrade() -> None:
    # Remove test_method column from serology_results table
    op.drop_column('serology_results', 'test_method')

