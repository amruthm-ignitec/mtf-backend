"""fix_userrole_enum_case_issues

Revision ID: fix_userrole_case
Revises: 09cb35b9b49c
Create Date: 2026-01-05 13:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fix_userrole_case'
down_revision = '09cb35b9b49c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Fix any existing uppercase role values in the users table.
    This migration converts any 'ADMIN', 'DOC_UPLOADER', or 'MEDICAL_DIRECTOR' 
    values to their lowercase equivalents.
    """
    conn = op.get_bind()
    
    # Check if users table exists
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'users'
        )
    """))
    
    if not result.scalar():
        # Table doesn't exist, skip migration
        return
    
    # Fix any uppercase role values
    # Convert 'ADMIN' -> 'admin'
    conn.execute(sa.text("""
        UPDATE users 
        SET role = 'admin' 
        WHERE role::text = 'ADMIN'
    """))
    
    # Convert 'DOC_UPLOADER' -> 'doc_uploader'
    conn.execute(sa.text("""
        UPDATE users 
        SET role = 'doc_uploader' 
        WHERE role::text = 'DOC_UPLOADER'
    """))
    
    # Convert 'MEDICAL_DIRECTOR' -> 'medical_director'
    conn.execute(sa.text("""
        UPDATE users 
        SET role = 'medical_director' 
        WHERE role::text = 'MEDICAL_DIRECTOR'
    """))
    
    # Also handle any case variations (e.g., 'Admin', 'Doc_Uploader', etc.)
    # Convert to lowercase
    conn.execute(sa.text("""
        UPDATE users 
        SET role = LOWER(role::text)::userrole
        WHERE role::text != LOWER(role::text)
    """))


def downgrade() -> None:
    # No downgrade needed - this is a data fix, not a schema change
    pass

