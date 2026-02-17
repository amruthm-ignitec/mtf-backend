"""Load configuration from environment (e.g. .env)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database (use DATABASE_URL in .env; for async use postgresql+asyncpg://...)
    database_url: str = "postgresql+asyncpg://localhost:5432/donoriq_db"

    @property
    def database_url_async(self) -> str:
        url = self.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    # Azure Document Intelligence
    azure_doc_intel_endpoint: str = ""
    azure_doc_intel_key: str = ""

    # Azure OpenAI
    azure_openai_endpoint: str = ""
    azure_openai_key: str = ""
    azure_openai_deployment: str = "gpt-4o"

    # File upload (POC: local storage)
    upload_dir: str = "uploads"
    max_file_size_mb: int = 500

    # Server (for run script; uvicorn CLI can override with --port)
    port: int = 8000
    host: str = "0.0.0.0"


def get_settings() -> Settings:
    return Settings()
