from pydantic_settings import BaseSettings
from typing import List, Optional
import os
import secrets

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://mtf_own2_user:rosjM5kvgdESPtx2FvXpSzIjd3D9XYa9@dpg-d3ufe9e3jp1c73a92h20-a.oregon-postgres.render.com/mtf_own2"
    
    # JWT
    SECRET_KEY: str = "donoriq-secret-key-for-development-only-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Azure Blob Storage
    AZURE_STORAGE_ACCOUNT_NAME: str = ""
    AZURE_STORAGE_ACCOUNT_KEY: str = ""
    AZURE_STORAGE_CONTAINER_NAME: str = "documents"
    
    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-ada-002"
    OPENAI_SUMMARIZATION_MODEL: str = "gpt-3.5-turbo"
    
    # Application
    DEBUG: bool = False
    ENVIRONMENT: str = "production"
    APP_NAME: str = "DonorIQ API"
    APP_VERSION: str = "1.0.0"
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173", "http://127.0.0.1:3000"]
    
    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4
    
    # File Upload
    MAX_FILE_SIZE_MB: int = 500
    ALLOWED_FILE_TYPES: List[str] = ["pdf", "doc", "docx", "txt", "jpg", "jpeg", "png"]
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
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        env_file_encoding = "utf-8"

settings = Settings()
