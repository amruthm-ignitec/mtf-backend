"""Add donor approvals table

Revision ID: add_donor_approvals
Revises: cb292b7f4abc
Create Date: 2025-01-XX XX:XX:XX.XXXXXX

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_donor_approvals'
down_revision = 'cb292b7f4abc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    
    # Check if table already exists
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'donor_approvals'
        )
    """))
    
    if result.scalar():
        # Table already exists, skip migration
        return
    
    # Create enums using raw SQL to avoid conflicts
    conn.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE approvalstatus AS ENUM ('approved', 'rejected', 'pending');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """))
    
    conn.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE approvaltype AS ENUM ('document', 'donor_summary');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """))
    
    # Create donor_approvals table
    op.create_table('donor_approvals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('donor_id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=True),
        sa.Column('approval_type', sa.Enum('document', 'donor_summary', name='approvaltype', create_type=False), nullable=False),
        sa.Column('status', sa.Enum('approved', 'rejected', 'pending', name='approvalstatus', create_type=False), nullable=False),
        sa.Column('comment', sa.Text(), nullable=False),
        sa.Column('approved_by', sa.Integer(), nullable=False),
        sa.Column('checklist_data', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['donor_id'], ['donors.id'], ),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_donor_approvals_id'), 'donor_approvals', ['id'], unique=False)
    op.create_index(op.f('ix_donor_approvals_donor_id'), 'donor_approvals', ['donor_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_donor_approvals_donor_id'), table_name='donor_approvals')
    op.drop_index(op.f('ix_donor_approvals_id'), table_name='donor_approvals')
    op.drop_table('donor_approvals')
    
    # Drop enums
    sa.Enum(name='approvalstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='approvaltype').drop(op.get_bind(), checkfirst=True)

