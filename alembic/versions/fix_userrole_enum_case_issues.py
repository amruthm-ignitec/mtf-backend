"""fix_userrole_enum_case_issues

Revision ID: fix_userrole_case
Revises: merge_heads
Create Date: 2026-01-05 13:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fix_userrole_case'
down_revision = 'merge_heads'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Ensure userrole enum exists with correct values and fix any data issues.
    This migration:
    1. Creates the enum type if it doesn't exist
    2. Fixes any uppercase role values in the users table
    3. Handles case variations
    """
    conn = op.get_bind()
    
    # Step 1: Ensure the enum type exists with correct values
    # Check if enum exists
    enum_exists = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_type 
            WHERE typname = 'userrole'
        )
    """)).scalar()
    
    if not enum_exists:
        # Create the enum type
        conn.execute(sa.text("""
            CREATE TYPE userrole AS ENUM ('admin', 'doc_uploader', 'medical_director')
        """))
    else:
        # Check if enum has correct values
        enum_values = conn.execute(sa.text("""
            SELECT enumlabel 
            FROM pg_enum 
            WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'userrole')
            ORDER BY enumsortorder
        """)).fetchall()
        
        existing_values = [row[0] for row in enum_values]
        required_values = ['admin', 'doc_uploader', 'medical_director']
        
        # If enum values don't match, we need to recreate it
        if set(existing_values) != set(required_values):
            # First, check if users table exists and has data
            users_exist = conn.execute(sa.text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'users'
                )
            """)).scalar()
            
            if users_exist:
                # Temporarily change column type to text
                conn.execute(sa.text("""
                    ALTER TABLE users ALTER COLUMN role TYPE text
                """))
            
            # Drop and recreate enum
            conn.execute(sa.text("DROP TYPE IF EXISTS userrole CASCADE"))
            conn.execute(sa.text("""
                CREATE TYPE userrole AS ENUM ('admin', 'doc_uploader', 'medical_director')
            """))
            
            if users_exist:
                # Convert back to enum, normalizing values
                conn.execute(sa.text("""
                    ALTER TABLE users 
                    ALTER COLUMN role TYPE userrole 
                    USING LOWER(role)::userrole
                """))
    
    # Step 2: Fix any uppercase role values in users table (if table exists)
    users_exist = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'users'
        )
    """)).scalar()
    
    if users_exist:
        # Fix any uppercase role values
        # Convert 'ADMIN' -> 'admin'
        conn.execute(sa.text("""
            UPDATE users 
            SET role = 'admin'::userrole
            WHERE role::text = 'ADMIN'
        """))
        
        # Convert 'DOC_UPLOADER' -> 'doc_uploader'
        conn.execute(sa.text("""
            UPDATE users 
            SET role = 'doc_uploader'::userrole
            WHERE role::text = 'DOC_UPLOADER'
        """))
        
        # Convert 'MEDICAL_DIRECTOR' -> 'medical_director'
        conn.execute(sa.text("""
            UPDATE users 
            SET role = 'medical_director'::userrole
            WHERE role::text = 'MEDICAL_DIRECTOR'
        """))
        
        # Also handle any case variations (e.g., 'Admin', 'Doc_Uploader', etc.)
        # Convert to lowercase - but only if the value is not already lowercase
        conn.execute(sa.text("""
            UPDATE users 
            SET role = LOWER(role::text)::userrole
            WHERE role::text != LOWER(role::text)
        """))


def downgrade() -> None:
    # No downgrade needed - this is a data fix, not a schema change
    pass

