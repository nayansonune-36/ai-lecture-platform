"""Application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"

    # Database
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres_dev_password@localhost:5432/lecture_platform"
    )

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Storage
    storage_root: Path = Path("./storage")
    max_upload_size_bytes: int = 8 * 1024 * 1024 * 1024  # 8 GB default

    # Auth & Tokens
    secret_key: str = "dev-insecure-secret-key-change-in-production"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 14

    # Media Signing
    media_signing_key: str = "dev-insecure-media-signing-key-change-in-production"
    media_url_expire_minutes: int = 15

    # Offline License Signing (Ed25519 PKCS8 PEM or seed)
    license_signing_key: str = ""

    # AI Models (Ollama)
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "bge-m3"
    llm_model: str = "qwen2.5:7b"

    # Caddy
    caddy_http_port: int = 8080
    caddy_https_port: int = 8443

    @field_validator("storage_root", mode="after")
    @classmethod
    def resolve_storage_root(cls, v: Path) -> Path:
        """Resolve storage root path whether run from root or services/api."""
        if v.is_absolute():
            return v
        cwd_path = (Path.cwd() / v).resolve()
        if cwd_path.exists():
            return cwd_path
        # Fallback to repo root (four levels above this file: app/ -> api/ -> services/ -> root)
        repo_root = Path(__file__).resolve().parents[3]
        repo_path = (repo_root / v).resolve()
        if repo_path.exists():
            return repo_path
        return cwd_path

    @property
    def resolved_storage_root(self) -> Path:
        """Alias for storage_root matching worker settings convention."""
        return self.storage_root


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
