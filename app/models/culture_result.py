from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.database import Base

class CultureResult(Base):
    __tablename__ = "culture_results"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    
    # For tissue cultures (legacy format)
    tissue_location = Column(String, nullable=True)  # e.g., "Left Hemipelvis Pre-Processing Culture"
    microorganism = Column(String, nullable=True)  # e.g., "Listeria monocytogenes"
    
    # For all culture types (new format, similar to serology)
    test_name = Column(String, nullable=True)  # e.g., "Blood Culture", "Urine Culture", "Tissue Culture"
    test_method = Column(String, nullable=True)  # e.g., "Urine Culture", "Molecular ID", "Blood Culture Gram Stain"
    specimen_type = Column(String, nullable=True)  # e.g., "Urine, Clean Catch", "Blood"
    specimen_date = Column(String, nullable=True)  # e.g., "05/12/2025 23:30 EDT"
    result = Column(String, nullable=True)  # e.g., "No growth", "Staphylococcus epidermidis - Detected"
    comments = Column(Text, nullable=True)  # Additional comments
    
    source_page = Column(Integer, nullable=True)  # Page number where found
    confidence = Column(Float, nullable=True)  # Confidence score if available
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("Document", backref="culture_results")

