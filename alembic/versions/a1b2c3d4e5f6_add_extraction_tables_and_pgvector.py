"""Add extraction tables and pgvector support

Revision ID: a1b2c3d4e5f6
Revises: 965785d01084
Create Date: 2025-01-27 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '965785d01084'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    
    conn = op.get_bind()
    
    # Create culture_results table
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'culture_results'
        )
    """))
    
    if not result.scalar():
        op.create_table('culture_results',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('document_id', sa.Integer(), nullable=False),
            sa.Column('tissue_location', sa.String(), nullable=False),
            sa.Column('microorganism', sa.String(), nullable=False),
            sa.Column('source_page', sa.Integer(), nullable=True),
            sa.Column('confidence', sa.Float(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_culture_results_id'), 'culture_results', ['id'], unique=False)
        op.create_index(op.f('ix_culture_results_document_id'), 'culture_results', ['document_id'], unique=False)
    
    # Create serology_results table
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'serology_results'
        )
    """))
    
    if not result.scalar():
        op.create_table('serology_results',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('document_id', sa.Integer(), nullable=False),
            sa.Column('test_name', sa.String(), nullable=False),
            sa.Column('result', sa.String(), nullable=False),
            sa.Column('source_page', sa.Integer(), nullable=True),
            sa.Column('confidence', sa.Float(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_serology_results_id'), 'serology_results', ['id'], unique=False)
        op.create_index(op.f('ix_serology_results_document_id'), 'serology_results', ['document_id'], unique=False)
    
    # Create topic_results table
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'topic_results'
        )
    """))
    
    if not result.scalar():
        op.create_table('topic_results',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('document_id', sa.Integer(), nullable=False),
            sa.Column('topic_name', sa.String(), nullable=False),
            sa.Column('summary', sa.Text(), nullable=True),
            sa.Column('citations', postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column('source_pages', postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_topic_results_id'), 'topic_results', ['id'], unique=False)
        op.create_index(op.f('ix_topic_results_document_id'), 'topic_results', ['document_id'], unique=False)
        op.create_index(op.f('ix_topic_results_topic_name'), 'topic_results', ['topic_name'], unique=False)
    
    # Create component_results table
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'component_results'
        )
    """))
    
    if not result.scalar():
        op.create_table('component_results',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('document_id', sa.Integer(), nullable=False),
            sa.Column('component_name', sa.String(), nullable=False),
            sa.Column('present', sa.Boolean(), nullable=False),
            sa.Column('pages', postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column('summary', sa.Text(), nullable=True),
            sa.Column('extracted_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_component_results_id'), 'component_results', ['id'], unique=False)
        op.create_index(op.f('ix_component_results_document_id'), 'component_results', ['document_id'], unique=False)
        op.create_index(op.f('ix_component_results_component_name'), 'component_results', ['component_name'], unique=False)
    
    # Create donor_extractions table
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'donor_extractions'
        )
    """))
    
    if not result.scalar():
        op.create_table('donor_extractions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('donor_id', sa.Integer(), nullable=False),
            sa.Column('extraction_data', postgresql.JSON(astext_type=sa.Text()), nullable=False),
            sa.Column('last_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.Column('documents_processed', sa.Integer(), nullable=True),
            sa.Column('processing_status', sa.String(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.ForeignKeyConstraint(['donor_id'], ['donors.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('donor_id')
        )
        op.create_index(op.f('ix_donor_extractions_id'), 'donor_extractions', ['id'], unique=False)
        op.create_index(op.f('ix_donor_extractions_donor_id'), 'donor_extractions', ['donor_id'], unique=True)
    
    # Create document_chunks table with pgvector
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'document_chunks'
        )
    """))
    
    if not result.scalar():
        op.create_table('document_chunks',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('document_id', sa.Integer(), nullable=False),
            sa.Column('chunk_text', sa.Text(), nullable=False),
            sa.Column('chunk_index', sa.Integer(), nullable=False),
            sa.Column('page_number', sa.Integer(), nullable=True),
            sa.Column('chunk_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        # Add vector column using raw SQL (pgvector)
        op.execute("ALTER TABLE document_chunks ADD COLUMN embedding vector(1536);")
        op.create_index(op.f('ix_document_chunks_id'), 'document_chunks', ['id'], unique=False)
        op.create_index(op.f('ix_document_chunks_document_id'), 'document_chunks', ['document_id'], unique=False)
        # Create vector similarity index
        op.execute("CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx ON document_chunks USING ivfflat (embedding vector_cosine_ops);")
    
    # Create donor_extraction_vectors table with pgvector
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'donor_extraction_vectors'
        )
    """))
    
    if not result.scalar():
        op.create_table('donor_extraction_vectors',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('donor_id', sa.Integer(), nullable=False),
            sa.Column('extraction_type', sa.String(), nullable=False),
            sa.Column('extraction_text', sa.Text(), nullable=False),
            sa.Column('extraction_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.ForeignKeyConstraint(['donor_id'], ['donors.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        # Add vector column using raw SQL (pgvector)
        op.execute("ALTER TABLE donor_extraction_vectors ADD COLUMN embedding vector(1536);")
        op.create_index(op.f('ix_donor_extraction_vectors_id'), 'donor_extraction_vectors', ['id'], unique=False)
        op.create_index(op.f('ix_donor_extraction_vectors_donor_id'), 'donor_extraction_vectors', ['donor_id'], unique=False)
        op.create_index(op.f('ix_donor_extraction_vectors_extraction_type'), 'donor_extraction_vectors', ['extraction_type'], unique=False)
        # Create vector similarity index
        op.execute("CREATE INDEX IF NOT EXISTS donor_extraction_vectors_embedding_idx ON donor_extraction_vectors USING ivfflat (embedding vector_cosine_ops);")


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index('donor_extraction_vectors_embedding_idx', table_name='donor_extraction_vectors')
    op.drop_index(op.f('ix_donor_extraction_vectors_extraction_type'), table_name='donor_extraction_vectors')
    op.drop_index(op.f('ix_donor_extraction_vectors_donor_id'), table_name='donor_extraction_vectors')
    op.drop_index(op.f('ix_donor_extraction_vectors_id'), table_name='donor_extraction_vectors')
    op.drop_table('donor_extraction_vectors')
    
    op.drop_index('document_chunks_embedding_idx', table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_document_id'), table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_id'), table_name='document_chunks')
    op.drop_table('document_chunks')
    
    op.drop_index(op.f('ix_donor_extractions_donor_id'), table_name='donor_extractions')
    op.drop_index(op.f('ix_donor_extractions_id'), table_name='donor_extractions')
    op.drop_table('donor_extractions')
    
    op.drop_index(op.f('ix_component_results_component_name'), table_name='component_results')
    op.drop_index(op.f('ix_component_results_document_id'), table_name='component_results')
    op.drop_index(op.f('ix_component_results_id'), table_name='component_results')
    op.drop_table('component_results')
    
    op.drop_index(op.f('ix_topic_results_topic_name'), table_name='topic_results')
    op.drop_index(op.f('ix_topic_results_document_id'), table_name='topic_results')
    op.drop_index(op.f('ix_topic_results_id'), table_name='topic_results')
    op.drop_table('topic_results')
    
    op.drop_index(op.f('ix_serology_results_document_id'), table_name='serology_results')
    op.drop_index(op.f('ix_serology_results_id'), table_name='serology_results')
    op.drop_table('serology_results')
    
    op.drop_index(op.f('ix_culture_results_document_id'), table_name='culture_results')
    op.drop_index(op.f('ix_culture_results_id'), table_name='culture_results')
    op.drop_table('culture_results')
    
    # Note: We don't drop the vector extension as it might be used by other tables

