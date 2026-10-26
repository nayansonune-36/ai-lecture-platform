"""Application settings loaded from environment variables."""

import os
import uuid
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
ROOT_ENV = REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Application configuration settings."""

    model_config = SettingsConfigDict(
        env_file=str(ROOT_ENV),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"

    # Database
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres_dev_password@127.0.0.1:5432/lecture_platform"
    )

    # Redis
    redis_url: str = "redis://127.0.0.1:6379/0"

    # Storage
    storage_root: Path = (REPO_ROOT / "storage").resolve()
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
    # Dev-only setting for testing license expiry quickly (default 14 days in seconds)
    license_ttl_seconds: int = 14 * 24 * 3600

    # AI Models (Ollama)
    ollama_base_url: str = "http://127.0.0.1:11434"
    embedding_model: str = "bge-m3"
    llm_model: str = "qwen2.5:7b"

    # Caddy
    caddy_http_port: int = 8080
    caddy_https_port: int = 8443

    @field_validator("storage_root", mode="after")
    @classmethod
    def validate_storage_root(cls, v: Path) -> Path:
        """Ensure STORAGE_ROOT is an absolute path and is writable."""
        if not v.is_absolute():
            raise ValueError(
                f"STORAGE_ROOT must be an absolute path, got relative path '{v}'. "
                "Relative paths resolve differently across API, Worker, and Caddy. "
                "Run scripts/setup-dev.ps1 or set an absolute path in .env."
            )
        resolved = v.resolve()
        try:
            resolved.mkdir(parents=True, exist_ok=True)
            probe = resolved / f".probe_write_{os.getpid()}_{uuid.uuid4().hex[:8]}"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except Exception as exc:
            raise ValueError(
                f"STORAGE_ROOT '{resolved}' is not writable or cannot be created: {exc}. "
                "Please check folder permissions."
            ) from exc
        return resolved

    @property
    def resolved_storage_root(self) -> Path:
        """Alias for storage_root matching worker settings convention."""
        return self.storage_root


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
