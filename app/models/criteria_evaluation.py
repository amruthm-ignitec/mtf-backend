from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.database import Base
import enum

class EvaluationResult(str, enum.Enum):
    ACCEPTABLE = "acceptable"
    UNACCEPTABLE = "unacceptable"
    MD_DISCRETION = "md_discretion"

class TissueType(str, enum.Enum):
    MUSCULOSKELETAL = "musculoskeletal"
    SKIN = "skin"
    BOTH = "both"

class CriteriaEvaluation(Base):
    __tablename__ = "criteria_evaluations"
    
    id = Column(Integer, primary_key=True, index=True)
    donor_id = Column(Integer, ForeignKey("donors.id"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True, index=True)  # Nullable if criterion spans multiple docs
    
    # Criterion identification
    criterion_name = Column(String, nullable=False, index=True)  # e.g., "Cancer", "HIV", "Sepsis"
    tissue_type = Column(Enum(TissueType, native_enum=False, values_callable=lambda x: [e.value for e in x]), nullable=False, index=True)  # Which tissue type this evaluation is for
    
    # Extracted data and evaluation
    extracted_data = Column(JSON, nullable=True)  # Raw extracted data for this criterion
    evaluation_result = Column(Enum(EvaluationResult, native_enum=False, values_callable=lambda x: [e.value for e in x]), nullable=False)  # Acceptable/Unacceptable/MD Discretion
    evaluation_reasoning = Column(Text, nullable=True)  # Explanation of the evaluation
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    donor = relationship("Donor", backref="criteria_evaluations")
    document = relationship("Document", backref="criteria_evaluations")

