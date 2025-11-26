from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.database import Base

class CultureResult(Base):
    __tablename__ = "culture_results"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    tissue_location = Column(String, nullable=False)  # e.g., "Left Hemipelvis Pre-Processing Culture"
    microorganism = Column(String, nullable=False)  # e.g., "Listeria monocytogenes"
    source_page = Column(Integer, nullable=True)  # Page number where found
    confidence = Column(Float, nullable=True)  # Confidence score if available
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("Document", backref="culture_results")

