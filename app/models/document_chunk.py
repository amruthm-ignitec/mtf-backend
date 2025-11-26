from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.database import Base

# Note: pgvector extension needs to be installed in PostgreSQL
# The vector type will be handled in the migration
try:
    from pgvector.sqlalchemy import Vector
    VECTOR_AVAILABLE = True
except ImportError:
    # Fallback for development without pgvector installed
    VECTOR_AVAILABLE = False
    Vector = None

class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    chunk_text = Column(Text, nullable=False)  # The actual text content of the chunk
    chunk_index = Column(Integer, nullable=False)  # Order of chunk in document
    page_number = Column(Integer, nullable=True)  # Page number where chunk is from
    embedding = Column(Vector(1536), nullable=True) if VECTOR_AVAILABLE else Column(JSON, nullable=True)  # Vector embedding (1536 dimensions for text-embedding-3-large)
    chunk_metadata = Column(JSON, nullable=True)  # Additional metadata about the chunk (renamed from 'metadata' to avoid SQLAlchemy conflict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("Document", backref="chunks")

