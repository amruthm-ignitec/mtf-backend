from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, TypeDecorator
from sqlalchemy.sql import func
from app.database.database import Base
import enum

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    DOC_UPLOADER = "doc_uploader"
    MEDICAL_DIRECTOR = "medical_director"

class UserRoleType(TypeDecorator):
    """
    Custom type decorator that handles case-insensitive conversion for UserRole enum.
    This prevents LookupError when database contains uppercase values like 'ADMIN'.
    """
    impl = Enum
    cache_ok = True
    
    def __init__(self):
        super().__init__(
            UserRole,
            native_enum=False,
            values_callable=lambda x: [e.value for e in x]
        )
    
    def process_result_value(self, value, dialect):
        """Convert database value to enum, handling case-insensitive matching."""
        if value is None:
            return None
        
        # If it's already a UserRole enum, return it
        if isinstance(value, UserRole):
            return value
        
        # Convert to string and normalize to lowercase
        value_str = str(value).lower()
        
        # Map common variations to correct enum values
        role_mapping = {
            'admin': UserRole.ADMIN,
            'doc_uploader': UserRole.DOC_UPLOADER,
            'doc uploader': UserRole.DOC_UPLOADER,
            'medical_director': UserRole.MEDICAL_DIRECTOR,
            'medical director': UserRole.MEDICAL_DIRECTOR,
        }
        
        # Try exact match first
        try:
            return UserRole(value_str)
        except ValueError:
            # Try mapping
            if value_str in role_mapping:
                return role_mapping[value_str]
            # If still not found, log warning and return ADMIN as fallback
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Unknown user role value '{value}', defaulting to ADMIN")
            return UserRole.ADMIN

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(UserRoleType(), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


