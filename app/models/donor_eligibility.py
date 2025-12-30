from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.database import Base
import enum

class EligibilityStatus(str, enum.Enum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    REQUIRES_REVIEW = "requires_review"

class TissueType(str, enum.Enum):
    MUSCULOSKELETAL = "musculoskeletal"
    SKIN = "skin"

class DonorEligibility(Base):
    __tablename__ = "donor_eligibility"
    
    id = Column(Integer, primary_key=True, index=True)
    donor_id = Column(Integer, ForeignKey("donors.id"), nullable=False, index=True)
    tissue_type = Column(Enum(TissueType, native_enum=False, values_callable=lambda x: [e.value for e in x]), nullable=False, index=True)
    
    # Eligibility decision
    overall_status = Column(Enum(EligibilityStatus, native_enum=False, values_callable=lambda x: [e.value for e in x]), nullable=False)  # eligible/ineligible/requires_review
    
    # Criteria details
    blocking_criteria = Column(JSON, nullable=True)  # List of criteria that make donor ineligible
    md_discretion_criteria = Column(JSON, nullable=True)  # List of criteria requiring medical director review
    
    # Evaluation metadata
    evaluated_at = Column(DateTime(timezone=True), server_default=func.now())
    evaluated_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # User who evaluated (null if auto-evaluated)
    
    # Relationships
    donor = relationship("Donor", backref="eligibility_decisions")
    evaluator = relationship("User", foreign_keys=[evaluated_by])

