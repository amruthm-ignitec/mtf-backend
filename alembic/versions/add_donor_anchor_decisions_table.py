"""Add donor anchor decisions table

Revision ID: add_donor_anchor_decisions
Revises: add_culture_fields
Create Date: 2025-01-XX XX:XX:XX.XXXXXX

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_donor_anchor_decisions'
down_revision = 'add_culture_fields'  # Updated to point to the actual latest migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    
    # Check if table already exists
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'donor_anchor_decisions'
        )
    """))
    
    if result.scalar():
        # Table already exists, skip migration
        return
    
    # Ensure pgvector extension is enabled
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    
    # Check if enums exist before creating them
    # Check for anchoroutcome enum
    enum_check = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_type WHERE typname = 'anchoroutcome'
        )
    """))
    
    if not enum_check.scalar():
        # Create anchoroutcome enum
        conn.execute(sa.text("CREATE TYPE anchoroutcome AS ENUM ('accepted', 'rejected');"))
    
    # Check for outcomesource enum
    enum_check2 = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_type WHERE typname = 'outcomesource'
        )
    """))
    
    if not enum_check2.scalar():
        # Create outcomesource enum
        conn.execute(sa.text("CREATE TYPE outcomesource AS ENUM ('batch_import', 'manual_approval', 'predicted');"))
    
    # Create donor_anchor_decisions table using raw SQL to avoid SQLAlchemy enum creation issues
    op.execute("""
        CREATE TABLE IF NOT EXISTS donor_anchor_decisions (
            id SERIAL PRIMARY KEY,
            donor_id INTEGER NOT NULL REFERENCES donors(id),
            outcome anchoroutcome NOT NULL,
            outcome_source outcomesource NOT NULL,
            parameter_snapshot JSONB NOT NULL,
            similarity_threshold_used FLOAT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE,
            parameter_embedding vector(3072)
        );
    """)
    
    # Create indexes (table already created with vector column above)
    op.execute("CREATE INDEX IF NOT EXISTS ix_donor_anchor_decisions_id ON donor_anchor_decisions(id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_donor_anchor_decisions_donor_id ON donor_anchor_decisions(donor_id);")
    
    # Create vector similarity index
    op.execute("""
        CREATE INDEX IF NOT EXISTS donor_anchor_decisions_embedding_idx 
        ON donor_anchor_decisions 
        USING ivfflat (parameter_embedding vector_cosine_ops)
        WITH (lists = 100);
    """)


def downgrade() -> None:
    op.drop_index(op.f('ix_donor_anchor_decisions_donor_id'), table_name='donor_anchor_decisions')
    op.drop_index(op.f('ix_donor_anchor_decisions_id'), table_name='donor_anchor_decisions')
    
    # Drop vector index
    op.execute("DROP INDEX IF EXISTS donor_anchor_decisions_embedding_idx;")
    
    # Drop vector column
    op.execute("ALTER TABLE donor_anchor_decisions DROP COLUMN IF EXISTS parameter_embedding;")
    
    op.drop_table('donor_anchor_decisions')
    
    # Drop enums
    sa.Enum(name='anchoroutcome').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='outcomesource').drop(op.get_bind(), checkfirst=True)

