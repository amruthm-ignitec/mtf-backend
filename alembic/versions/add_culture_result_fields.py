"""Add new fields to culture_results table for all culture types

Revision ID: add_culture_fields
Revises: add_test_method_serology
Create Date: 2025-12-02 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_culture_fields'
down_revision = 'add_test_method_serology'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make existing columns nullable and add new columns
    conn = op.get_bind()
    
    # Check if columns exist first (idempotent)
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = 'culture_results' 
            AND column_name = 'test_name'
        )
    """))
    
    if not result.scalar():
        # Make tissue_location and microorganism nullable
        op.alter_column('culture_results', 'tissue_location', nullable=True)
        op.alter_column('culture_results', 'microorganism', nullable=True)
        
        # Add new columns for all culture types
        op.add_column('culture_results', sa.Column('test_name', sa.String(), nullable=True))
        op.add_column('culture_results', sa.Column('test_method', sa.String(), nullable=True))
        op.add_column('culture_results', sa.Column('specimen_type', sa.String(), nullable=True))
        op.add_column('culture_results', sa.Column('specimen_date', sa.String(), nullable=True))
        op.add_column('culture_results', sa.Column('result', sa.String(), nullable=True))
        op.add_column('culture_results', sa.Column('comments', sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove new columns and restore old constraints
    op.drop_column('culture_results', 'comments')
    op.drop_column('culture_results', 'result')
    op.drop_column('culture_results', 'specimen_date')
    op.drop_column('culture_results', 'specimen_type')
    op.drop_column('culture_results', 'test_method')
    op.drop_column('culture_results', 'test_name')
    
    # Restore not-null constraints (may fail if there are null values)
    op.alter_column('culture_results', 'microorganism', nullable=False)
    op.alter_column('culture_results', 'tissue_location', nullable=False)

