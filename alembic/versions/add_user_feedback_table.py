"""add_user_feedback_table

Revision ID: add_user_feedback
Revises: add_donor_anchor_decisions
Create Date: 2025-01-XX XX:XX:XX.XXXXXX

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_user_feedback'
down_revision = 'add_donor_anchor_decisions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    
    # Check if table already exists
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'user_feedback'
        )
    """))
    
    if result.scalar():
        # Table already exists, skip migration
        return
    
    # Create user_feedback table
    op.execute("""
        CREATE TABLE user_feedback (
            id SERIAL PRIMARY KEY,
            username VARCHAR NOT NULL,
            feedback TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_feedback_id ON user_feedback(id);")


def downgrade() -> None:
    op.drop_index(op.f('ix_user_feedback_id'), table_name='user_feedback')
    op.drop_table('user_feedback')

