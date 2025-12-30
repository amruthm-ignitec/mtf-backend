from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Enum, TypeDecorator
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects import postgresql
from app.database.database import Base
import enum

class TestType(str, enum.Enum):
    SEROLOGY = "serology"
    CULTURE = "culture"
    OTHER = "other"

class TestTypeEnum(TypeDecorator):
    """Type decorator that casts to PostgreSQL enum type."""
    impl = String
    cache_ok = True
    
    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            # Use the existing enum type
            return dialect.type_descriptor(postgresql.ENUM('serology', 'culture', 'other', name='testtype', create_type=False))
        return dialect.type_descriptor(String)
    
    def process_bind_param(self, value, dialect):
        """Convert enum to value string for binding."""
        if value is None:
            return None
        if isinstance(value, TestType):
            return value.value
        return str(value)
    
    def process_result_value(self, value, dialect):
        """Convert database value back to enum."""
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return TestType(value)
            except ValueError:
                return value
        return value

class LaboratoryResult(Base):
    __tablename__ = "laboratory_results"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    
    # Test classification - Use TypeDecorator for PostgreSQL enum
    test_type = Column(TestTypeEnum, nullable=False, index=True)
    
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

