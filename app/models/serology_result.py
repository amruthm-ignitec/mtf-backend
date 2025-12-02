from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.database import Base

class SerologyResult(Base):
    __tablename__ = "serology_results"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    test_name = Column(String, nullable=False)  # e.g., "HIV", "HBV", "HCV" (cleaned, without method)
    test_method = Column(String, nullable=True)  # e.g., "Abbott Alinity s CMIA", "DiaSorin Liaison CLIA" (method/manufacturer)
    result = Column(String, nullable=False)  # e.g., "Negative", "Positive", "Reactive"
    source_page = Column(Integer, nullable=True)  # Page number where found
    confidence = Column(Float, nullable=True)  # Confidence score if available
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("Document", backref="serology_results")

