"""add_donor_feedback_table

Revision ID: add_donor_feedback
Revises: rename_to_platform_feedback
Create Date: 2026-01-XX XX:XX:XX.XXXXXX

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_donor_feedback'
down_revision = 'rename_to_platform_feedback'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    
    # Check if table already exists
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'donor_feedback'
        )
    """))
    
    if result.scalar():
        # Table already exists, skip migration
        return
    
    # Create donor_feedback table
    op.execute("""
        CREATE TABLE donor_feedback (
            id SERIAL PRIMARY KEY,
            donor_id INTEGER NOT NULL,
            username VARCHAR NOT NULL,
            feedback TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            CONSTRAINT fk_donor_feedback_donor 
                FOREIGN KEY (donor_id) 
                REFERENCES donors(id) 
                ON DELETE CASCADE
        );
    """)
    
    # Create indexes
    op.execute("CREATE INDEX IF NOT EXISTS ix_donor_feedback_id ON donor_feedback(id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_donor_feedback_donor_id ON donor_feedback(donor_id);")


def downgrade() -> None:
    op.drop_index(op.f('ix_donor_feedback_donor_id'), table_name='donor_feedback')
    op.drop_index(op.f('ix_donor_feedback_id'), table_name='donor_feedback')
    op.drop_table('donor_feedback')

