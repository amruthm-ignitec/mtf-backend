from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Enum
from sqlalchemy.sql import func
from app.database.database import Base
import enum

class SettingType(str, enum.Enum):
    OPENAI_API_KEY = "openai_api_key"
    OPENAI_EMBEDDING_MODEL = "openai_embedding_model"
    OPENAI_SUMMARIZATION_MODEL = "openai_summarization_model"
    AZURE_API_KEY = "azure_api_key"
    AZURE_ENDPOINT = "azure_endpoint"
    AZURE_DEPLOYMENT_ID = "azure_deployment_id"
    GOOGLE_API_KEY = "google_api_key"
    GOOGLE_PROJECT_ID = "google_project_id"
    ANTHROPIC_API_KEY = "anthropic_api_key"

class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(Enum(SettingType), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    is_encrypted = Column(Boolean, default=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
