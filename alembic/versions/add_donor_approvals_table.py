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
    
    # Check if enums exist before creating them
    enum_check1 = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_type WHERE typname = 'approvalstatus'
        )
    """))
    
    if not enum_check1.scalar():
        conn.execute(sa.text("CREATE TYPE approvalstatus AS ENUM ('approved', 'rejected', 'pending');"))
    
    enum_check2 = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_type WHERE typname = 'approvaltype'
        )
    """))
    
    if not enum_check2.scalar():
        conn.execute(sa.text("CREATE TYPE approvaltype AS ENUM ('document', 'donor_summary');"))
    
    # Create donor_approvals table using raw SQL to avoid SQLAlchemy enum creation issues
    op.execute("""
        CREATE TABLE donor_approvals (
            id SERIAL PRIMARY KEY,
            donor_id INTEGER NOT NULL REFERENCES donors(id),
            document_id INTEGER REFERENCES documents(id),
            approval_type approvaltype NOT NULL,
            status approvalstatus NOT NULL,
            comment TEXT NOT NULL,
            approved_by INTEGER NOT NULL REFERENCES users(id),
            checklist_data TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_donor_approvals_id ON donor_approvals(id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_donor_approvals_donor_id ON donor_approvals(donor_id);")


def downgrade() -> None:
    op.drop_index(op.f('ix_donor_approvals_donor_id'), table_name='donor_approvals')
    op.drop_index(op.f('ix_donor_approvals_id'), table_name='donor_approvals')
    op.drop_table('donor_approvals')
    
    # Drop enums
    sa.Enum(name='approvalstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='approvaltype').drop(op.get_bind(), checkfirst=True)

