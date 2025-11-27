from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
from pydantic import field_validator, Field
import os
import secrets
import json

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = ""
    
    # JWT
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Azure Blob Storage
    AZURE_STORAGE_ACCOUNT_NAME: str = ""
    AZURE_STORAGE_ACCOUNT_KEY: str = ""
    AZURE_STORAGE_CONTAINER_NAME: str = "documents"
    
    # OpenAI / Azure OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE: str = ""  # Azure OpenAI endpoint (e.g., https://YOUR-RESOURCE.openai.azure.com/)
    OPENAI_API_VERSION: str = "2023-07-01-preview"
    AZURE_OPENAI_CHAT_DEPLOYMENT_NAME: str = "gpt-4o"
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME: str = "text-embedding-3-large"
    AZURE_OPENAI_EMBEDDING_API_VERSION: str = "2023-05-15"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-ada-002"  # Legacy, can be removed
    OPENAI_SUMMARIZATION_MODEL: str = "gpt-3.5-turbo"  # Legacy, can be removed
    
    # Application
    DEBUG: bool = False
    ENVIRONMENT: str = "production"
    APP_NAME: str = "DonorIQ API"
    APP_VERSION: str = "1.0.0"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:3000"
    
    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4
    
    # File Upload
    MAX_FILE_SIZE_MB: int = 500
    ALLOWED_FILE_TYPES: str = "pdf,doc,docx,txt,jpg,jpeg,png"
    UPLOAD_DIRECTORY: str = "uploads"
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_FILE: str = "logs/app.log"
    
    # Security
    PASSWORD_MIN_LENGTH: int = 8
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 15
    BCRYPT_ROUNDS: int = 12
    
    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60  # seconds
    
    # Database Connection Pool
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 3600
    
    # Background Worker Configuration (asyncio-based)
    WORKER_ENABLED: bool = True
    WORKER_POLL_INTERVAL: int = 5  # seconds between queue polls
    WORKER_MAX_CONCURRENT: int = 3  # max documents processed simultaneously
    WORKER_MAX_RETRIES: int = 3  # max retry attempts for failed documents
    
    # Summary Deduplication
    ENABLE_SUMMARY_DEDUPLICATION: bool = True  # Enable LLM-based summary deduplication
    
    @field_validator('DEBUG', mode='before')
    @classmethod
    def parse_bool(cls, v):
        """Parse boolean from string."""
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return bool(v)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Convert comma-separated strings to lists after initialization
        self._cors_origins_list = [item.strip() for item in self.CORS_ORIGINS.split(',') if item.strip()]
        self._allowed_file_types_list = [item.strip() for item in self.ALLOWED_FILE_TYPES.split(',') if item.strip()]
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Get CORS_ORIGINS as a list."""
        return self._cors_origins_list
    
    @property
    def allowed_file_types_list(self) -> List[str]:
        """Get ALLOWED_FILE_TYPES as a list."""
        return self._allowed_file_types_list
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        env_file_encoding="utf-8",
    )

settings = Settings()
