"""rename_user_feedback_to_platform_feedback

Revision ID: rename_to_platform_feedback
Revises: fix_userrole_case
Create Date: 2026-01-XX XX:XX:XX.XXXXXX

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'rename_to_platform_feedback'
down_revision = 'fix_userrole_case'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    
    # Check if user_feedback table exists
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'user_feedback'
        )
    """))
    
    if not result.scalar():
        # Table doesn't exist, nothing to rename
        return
    
    # Check if platform_feedback table already exists
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'platform_feedback'
        )
    """))
    
    if result.scalar():
        # platform_feedback already exists, skip migration
        return
    
    # Rename the table
    op.rename_table('user_feedback', 'platform_feedback')
    
    # Rename the index
    op.execute("ALTER INDEX IF EXISTS ix_user_feedback_id RENAME TO ix_platform_feedback_id")


def downgrade() -> None:
    conn = op.get_bind()
    
    # Check if platform_feedback table exists
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'platform_feedback'
        )
    """))
    
    if not result.scalar():
        # Table doesn't exist, nothing to rename back
        return
    
    # Rename the index back
    op.execute("ALTER INDEX IF EXISTS ix_platform_feedback_id RENAME TO ix_user_feedback_id")
    
    # Rename the table back
    op.rename_table('platform_feedback', 'user_feedback')

