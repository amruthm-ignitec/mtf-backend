"""Update vector dimensions to 3072

Revision ID: update_vector_dimensions_3072
Revises: a44281be1c8f
Create Date: 2025-11-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'update_vector_dimensions_3072'
down_revision = 'a44281be1c8f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Update vector columns from 1536 to 3072 dimensions.
    This requires:
    1. Dropping existing indexes
    2. Altering column types
    3. Recreating indexes
    """
    conn = op.get_bind()
    
    # Check if document_chunks table exists and has embedding column
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_name = 'document_chunks' 
            AND column_name = 'embedding'
        )
    """))
    
    if result.scalar():
        # Drop existing vector index
        op.execute("DROP INDEX IF EXISTS document_chunks_embedding_idx;")
        
        # Clear existing embeddings (they're 1536 dimensions, need to regenerate as 3072)
        # This is necessary because we can't convert 1536-dim vectors to 3072-dim
        op.execute("UPDATE document_chunks SET embedding = NULL WHERE embedding IS NOT NULL;")
        
        # Alter column type from vector(1536) to vector(3072)
        op.execute("""
            ALTER TABLE document_chunks 
            ALTER COLUMN embedding TYPE vector(3072);
        """)
        
        # Recreate vector similarity index with new dimensions
        op.execute("""
            CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx 
            ON document_chunks 
            USING ivfflat (embedding vector_cosine_ops);
        """)
    
    # Check if donor_extraction_vectors table exists and has embedding column
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_name = 'donor_extraction_vectors' 
            AND column_name = 'embedding'
        )
    """))
    
    if result.scalar():
        # Drop existing vector index
        op.execute("DROP INDEX IF EXISTS donor_extraction_vectors_embedding_idx;")
        
        # Clear existing embeddings (they're 1536 dimensions, need to regenerate as 3072)
        op.execute("UPDATE donor_extraction_vectors SET embedding = NULL WHERE embedding IS NOT NULL;")
        
        # Alter column type from vector(1536) to vector(3072)
        op.execute("""
            ALTER TABLE donor_extraction_vectors 
            ALTER COLUMN embedding TYPE vector(3072);
        """)
        
        # Recreate vector similarity index with new dimensions
        op.execute("""
            CREATE INDEX IF NOT EXISTS donor_extraction_vectors_embedding_idx 
            ON donor_extraction_vectors 
            USING ivfflat (embedding vector_cosine_ops);
        """)


def downgrade() -> None:
    """
    Revert vector columns from 3072 back to 1536 dimensions.
    WARNING: This will truncate existing 3072-dimensional embeddings!
    """
    conn = op.get_bind()
    
    # Check if document_chunks table exists
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_name = 'document_chunks' 
            AND column_name = 'embedding'
        )
    """))
    
    if result.scalar():
        # Drop index
        op.execute("DROP INDEX IF EXISTS document_chunks_embedding_idx;")
        
        # Truncate embeddings to 1536 dimensions (take first 1536 elements)
        # Note: This causes data loss!
        op.execute("""
            ALTER TABLE document_chunks 
            ALTER COLUMN embedding TYPE vector(1536) 
            USING (embedding[1:1536])::vector(1536);
        """)
        
        # Recreate index
        op.execute("""
            CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx 
            ON document_chunks 
            USING ivfflat (embedding vector_cosine_ops);
        """)
    
    # Check if donor_extraction_vectors table exists
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_name = 'donor_extraction_vectors' 
            AND column_name = 'embedding'
        )
    """))
    
    if result.scalar():
        # Drop index
        op.execute("DROP INDEX IF EXISTS donor_extraction_vectors_embedding_idx;")
        
        # Truncate embeddings to 1536 dimensions
        op.execute("""
            ALTER TABLE donor_extraction_vectors 
            ALTER COLUMN embedding TYPE vector(1536) 
            USING (embedding[1:1536])::vector(1536);
        """)
        
        # Recreate index
        op.execute("""
            CREATE INDEX IF NOT EXISTS donor_extraction_vectors_embedding_idx 
            ON donor_extraction_vectors 
            USING ivfflat (embedding vector_cosine_ops);
        """)

