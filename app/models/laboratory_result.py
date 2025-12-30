from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.database import Base
import enum

class TestType(str, enum.Enum):
    SEROLOGY = "serology"
    CULTURE = "culture"
    OTHER = "other"

class LaboratoryResult(Base):
    __tablename__ = "laboratory_results"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    
    # Test classification
    test_type = Column(Enum(TestType), nullable=False, index=True)
    
    # Core test information (same for all types)
    test_name = Column(String, nullable=False)  # e.g., "HIV", "Blood Culture"
    test_method = Column(String, nullable=True)  # e.g., "Abbott Alinity", "Urine Culture"
    result = Column(String, nullable=False)  # e.g., "Negative", "No growth"
    
    # Culture-specific fields (nullable, only used for cultures)
    specimen_type = Column(String, nullable=True)  # e.g., "Blood", "Urine"
    specimen_date = Column(String, nullable=True)  # e.g., "05/12/2025"
    comments = Column(Text, nullable=True)
    
    # Legacy culture fields (for backward compatibility during transition)
    tissue_location = Column(String, nullable=True)  # Legacy: "Left Femur Recovery Culture"
    microorganism = Column(String, nullable=True)  # Legacy: "Staphylococcus epidermidis"
    
    # Metadata
    source_page = Column(Integer, nullable=True)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("Document", backref="laboratory_results")

