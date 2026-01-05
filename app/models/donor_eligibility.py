from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Enum, TypeDecorator
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects import postgresql
from app.database.database import Base
import enum

class EligibilityStatus(str, enum.Enum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    REQUIRES_REVIEW = "requires_review"

class TissueType(str, enum.Enum):
    MUSCULOSKELETAL = "musculoskeletal"
    SKIN = "skin"

class EligibilityTissueTypeEnum(TypeDecorator):
    """Type decorator that casts to PostgreSQL enum type."""
    impl = String
    cache_ok = True
    
    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            # Use the existing enum type
            return dialect.type_descriptor(postgresql.ENUM('musculoskeletal', 'skin', name='eligibilitytissuetype', create_type=False))
        return dialect.type_descriptor(String)
    
    def process_bind_param(self, value, dialect):
        """Convert enum to value string for binding."""
        if value is None:
            return None
        if isinstance(value, TissueType):
            return value.value
        return str(value)
    
    def process_result_value(self, value, dialect):
        """Convert database value back to enum."""
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return TissueType(value)
            except ValueError:
                return value
        return value

class EligibilityStatusEnum(TypeDecorator):
    """Type decorator that casts to PostgreSQL enum type."""
    impl = String
    cache_ok = True
    
    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            # Use the existing enum type
            return dialect.type_descriptor(postgresql.ENUM('eligible', 'ineligible', 'requires_review', name='eligibilitystatus', create_type=False))
        return dialect.type_descriptor(String)
    
    def process_bind_param(self, value, dialect):
        """Convert enum to value string for binding."""
        if value is None:
            return None
        if isinstance(value, EligibilityStatus):
            return value.value
        return str(value)
    
    def process_result_value(self, value, dialect):
        """Convert database value back to enum."""
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return EligibilityStatus(value)
            except ValueError:
                return value
        return value

class DonorEligibility(Base):
    __tablename__ = "donor_eligibility"
    
    id = Column(Integer, primary_key=True, index=True)
    donor_id = Column(Integer, ForeignKey("donors.id"), nullable=False, index=True)
    tissue_type = Column(EligibilityTissueTypeEnum(), nullable=False, index=True)
    
    # Eligibility decision
    overall_status = Column(EligibilityStatusEnum(), nullable=False)  # eligible/ineligible/requires_review
    
    # Criteria details
    blocking_criteria = Column(JSON, nullable=True)  # List of criteria that make donor ineligible
    md_discretion_criteria = Column(JSON, nullable=True)  # List of criteria requiring medical director review
    
    # Evaluation metadata
    evaluated_at = Column(DateTime(timezone=True), server_default=func.now())
    evaluated_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # User who evaluated (null if auto-evaluated)
    
    # Relationships
    donor = relationship("Donor", backref="eligibility_decisions")
    evaluator = relationship("User", foreign_keys=[evaluated_by])

