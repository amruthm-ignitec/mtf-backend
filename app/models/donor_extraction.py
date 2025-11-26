from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.database import Base

class DonorExtraction(Base):
    __tablename__ = "donor_extractions"
    
    id = Column(Integer, primary_key=True, index=True)
    donor_id = Column(Integer, ForeignKey("donors.id"), unique=True, nullable=False, index=True)
    extraction_data = Column(JSON, nullable=False)  # Full ExtractionDataResponse structure
    last_updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    documents_processed = Column(Integer, default=0)  # Count of contributing documents
    processing_status = Column(String, nullable=True)  # 'complete', 'partial', 'pending'
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    donor = relationship("Donor", backref="extraction")

