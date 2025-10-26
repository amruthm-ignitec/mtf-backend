from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.models.setting import SettingType

class SettingBase(BaseModel):
    key: SettingType
    value: Optional[str] = None
    is_encrypted: bool = False
    description: Optional[str] = None

class SettingCreate(SettingBase):
    pass

class SettingUpdate(BaseModel):
    value: Optional[str] = None
    description: Optional[str] = None

class SettingResponse(SettingBase):
    id: int
    created_at: str
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True

class SettingsResponse(BaseModel):
    openai_api_key: Optional[str] = None
    openai_embedding_model: Optional[str] = None
    openai_summarization_model: Optional[str] = None
    azure_api_key: Optional[str] = None
    azure_endpoint: Optional[str] = None
    azure_deployment_id: Optional[str] = None
    google_api_key: Optional[str] = None
    google_project_id: Optional[str] = None
    anthropic_api_key: Optional[str] = None

class SettingsUpdate(BaseModel):
    openai_api_key: Optional[str] = None
    openai_embedding_model: Optional[str] = None
    openai_summarization_model: Optional[str] = None
    azure_api_key: Optional[str] = None
    azure_endpoint: Optional[str] = None
    azure_deployment_id: Optional[str] = None
    google_api_key: Optional[str] = None
    google_project_id: Optional[str] = None
    anthropic_api_key: Optional[str] = None
