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

class DonorExtractionVector(Base):
    __tablename__ = "donor_extraction_vectors"
    
    id = Column(Integer, primary_key=True, index=True)
    donor_id = Column(Integer, ForeignKey("donors.id"), nullable=False, index=True)
    extraction_type = Column(String, nullable=False, index=True)  # 'culture', 'serology', 'topic', 'component'
    extraction_text = Column(Text, nullable=False)  # Textual representation of extracted data
    embedding = Column(Vector(3072), nullable=True) if VECTOR_AVAILABLE else Column(JSON, nullable=True)  # Vector embedding (3072 dimensions for text-embedding-3-large)
    extraction_metadata = Column(JSON, nullable=True)  # Original structured data (renamed from 'metadata' to avoid SQLAlchemy conflict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    donor = relationship("Donor", backref="extraction_vectors")

