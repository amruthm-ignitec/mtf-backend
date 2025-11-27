from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey, JSON, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.database import Base

class ComponentResult(Base):
    __tablename__ = "component_results"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    component_name = Column(String, nullable=False, index=True)  # e.g., "Donor Login Packet", "Physical Assessment"
    present = Column(Boolean, nullable=False, default=False)  # Whether component is present in document
    pages = Column(JSON, nullable=True)  # List of page numbers where component was found
    summary = Column(Text, nullable=True)  # Summary of component content
    extracted_data = Column(JSON, nullable=True)  # Structured extracted data for the component
    confidence = Column(Float, nullable=True)  # Confidence score (0.0-1.0 or 0-100) based on data completeness, page count, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("Document", backref="component_results")

