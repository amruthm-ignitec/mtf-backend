from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum, Float, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.database import Base
import enum

# Note: pgvector extension needs to be installed in PostgreSQL
# The vector type will be handled in the migration
try:
    from pgvector.sqlalchemy import Vector
    VECTOR_AVAILABLE = True
except ImportError:
    # Fallback for development without pgvector installed
    VECTOR_AVAILABLE = False
    Vector = None


class AnchorOutcome(str, enum.Enum):
    """Outcome for anchor decision."""
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class OutcomeSource(str, enum.Enum):
    """Source of the outcome decision."""
    BATCH_IMPORT = "batch_import"
    MANUAL_APPROVAL = "manual_approval"
    PREDICTED = "predicted"


class DonorAnchorDecision(Base):
    """Anchor database model for storing donor decisions with parameter snapshots."""
    __tablename__ = "donor_anchor_decisions"
    
    id = Column(Integer, primary_key=True, index=True)
    donor_id = Column(Integer, ForeignKey("donors.id"), nullable=False, index=True)
    outcome = Column(Enum(AnchorOutcome), nullable=False)
    outcome_source = Column(Enum(OutcomeSource), nullable=False, default=OutcomeSource.BATCH_IMPORT)
    parameter_snapshot = Column(JSON, nullable=False)  # Full parameter snapshot as JSON
    parameter_embedding = Column(Vector(3072), nullable=True) if VECTOR_AVAILABLE else Column(JSON, nullable=True)  # Vector embedding for similarity search
    similarity_threshold_used = Column(Float, nullable=True)  # Threshold used for similarity search (for tracking)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    donor = relationship("Donor", backref="anchor_decisions")

