from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Enum, TypeDecorator
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.dialects import postgresql
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

class CriteriaTissueTypeEnum(TypeDecorator):
    """Type decorator that casts to PostgreSQL enum type."""
    impl = String
    cache_ok = True
    
    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            # Use the existing enum type
            return dialect.type_descriptor(postgresql.ENUM('musculoskeletal', 'skin', 'both', name='criteriatissuetype', create_type=False))
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

class EvaluationResultEnum(TypeDecorator):
    """Type decorator that casts to PostgreSQL enum type."""
    impl = String
    cache_ok = True
    
    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            # Use the existing enum type
            return dialect.type_descriptor(postgresql.ENUM('acceptable', 'unacceptable', 'md_discretion', name='evaluationresult', create_type=False))
        return dialect.type_descriptor(String)
    
    def process_bind_param(self, value, dialect):
        """Convert enum to value string for binding."""
        if value is None:
            return None
        if isinstance(value, EvaluationResult):
            return value.value
        return str(value)
    
    def process_result_value(self, value, dialect):
        """Convert database value back to enum."""
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return EvaluationResult(value)
            except ValueError:
                return value
        return value

class CriteriaEvaluation(Base):
    __tablename__ = "criteria_evaluations"
    
    id = Column(Integer, primary_key=True, index=True)
    donor_id = Column(Integer, ForeignKey("donors.id"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True, index=True)  # Nullable if criterion spans multiple docs
    
    # Criterion identification
    criterion_name = Column(String, nullable=False, index=True)  # e.g., "Cancer", "HIV", "Sepsis"
    tissue_type = Column(CriteriaTissueTypeEnum(), nullable=False, index=True)  # Which tissue type this evaluation is for
    
    # Extracted data and evaluation
    extracted_data = Column(JSON, nullable=True)  # Raw extracted data for this criterion
    evaluation_result = Column(EvaluationResultEnum(), nullable=False)  # Acceptable/Unacceptable/MD Discretion
    evaluation_reasoning = Column(Text, nullable=True)  # Explanation of the evaluation
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    donor = relationship("Donor", backref="criteria_evaluations")
    document = relationship("Document", backref="criteria_evaluations")

