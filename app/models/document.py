from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, Text, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.database import Base
import enum

class DocumentStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    ANALYZING = "analyzing"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"

class DocumentType(str, enum.Enum):
    MEDICAL_HISTORY = "medical_history"
    SEROLOGY_REPORT = "serology_report"
    LAB_RESULTS = "lab_results"
    RECOVERY_CULTURES = "recovery_cultures"
    CONSENT_FORM = "consent_form"
    DEATH_CERTIFICATE = "death_certificate"
    OTHER = "other"

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)  # Size in bytes
    file_type = Column(String, nullable=False)  # MIME type
    document_type = Column(Enum(DocumentType), nullable=True)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.UPLOADED)
    progress = Column(Float, default=0.0)  # Processing progress 0-100
    azure_blob_url = Column(String, nullable=True)
    processing_result = Column(Text, nullable=True)  # AI analysis results
    error_message = Column(Text, nullable=True)  # Error details if processing fails
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Foreign Keys
    donor_id = Column(Integer, ForeignKey("donors.id"), nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Relationships
    donor = relationship("Donor", back_populates="documents", lazy="select")
    uploader = relationship("User", lazy="select")
