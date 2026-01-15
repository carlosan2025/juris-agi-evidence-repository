"""Application configuration using pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Evidence Repository"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    # API
    api_v1_prefix: str = "/api/v1"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Authentication
    api_keys_str: str = Field(default="dev-key-12345", alias="API_KEYS")
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    # Database
    database_url: str = "postgresql+asyncpg://evidence:evidence_secret@localhost:5432/evidence_repository"
    database_pool_size: int = 5
    database_max_overflow: int = 10

    # Storage
    storage_backend: Literal["local", "s3"] = "local"
    file_storage_root: str = Field(
        default="./data/files",
        alias="FILE_STORAGE_ROOT",
        description="Root directory for local file storage",
    )

    # S3 (for future use)
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    s3_bucket_name: str = "evidence-repository"
    s3_prefix: str = ""  # Optional key prefix for all S3 objects
    s3_endpoint_url: str | None = None  # Custom endpoint for S3-compatible services

    # LovePDF
    lovepdf_public_key: str = ""
    lovepdf_secret_key: str = ""

    # OpenAI
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536

    # Chunking
    chunk_size: int = 1000
    chunk_overlap: int = 200

    # CORS
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"])

    # Redis (Job Queue)
    redis_url: str = "redis://localhost:6379/0"
    redis_queue_name: str = "evidence_jobs"
    redis_job_timeout: int = 3600  # 1 hour default timeout
    redis_result_ttl: int = 86400  # 24 hours result retention

    # Bulk Ingestion
    bulk_ingestion_batch_size: int = 50
    url_download_timeout: int = 300  # 5 minutes for URL downloads
    max_file_size_mb: int = 100  # Max file size for uploads

    # Supported file types
    supported_extensions: list[str] = Field(
        default_factory=lambda: [
            ".pdf", ".txt", ".md", ".csv", ".xlsx", ".xls",
            ".docx", ".pptx",  # Microsoft Office
            ".png", ".jpg", ".jpeg", ".webp", ".html"
        ]
    )

    @property
    def api_keys(self) -> list[str]:
        """Parse comma-separated API keys string into list."""
        if not self.api_keys_str:
            return ["dev-key-12345"]
        return [k.strip() for k in self.api_keys_str.split(",") if k.strip()]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Parse CORS origins from JSON string or list."""
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [o.strip() for o in v.split(",") if o.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
