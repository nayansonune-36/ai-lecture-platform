"""Configuration settings for the ARQ worker service."""

import os
import shutil
import uuid
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT_ENV = REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Worker settings loaded from environment or .env file."""

    model_config = SettingsConfigDict(
        env_file=str(ROOT_ENV),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres_dev_password@127.0.0.1:5432/lecture_platform"
    )
    redis_url: str = "redis://127.0.0.1:6379/0"
    storage_root: Path = (REPO_ROOT / "storage").resolve()
    max_upload_size_bytes: int = 8 * 1024 * 1024 * 1024  # 8 GB

    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"

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
        """Resolve storage root to an absolute path."""
        return self.storage_root

    def get_ffmpeg_binary(self) -> str:
        """Return usable path to ffmpeg binary."""
        if shutil.which(self.ffmpeg_path):
            return self.ffmpeg_path

        # Check common Windows/custom fallback paths
        win_fallback = Path(r"C:\Users\Bleed\Youtube DLP\YT-DLP\ffmpeg.exe")
        if win_fallback.exists():
            return str(win_fallback)

        return self.ffmpeg_path

    def get_ffprobe_binary(self) -> str:
        """Return usable path to ffprobe binary."""
        if shutil.which(self.ffprobe_path):
            return self.ffprobe_path

        # Check common Windows/custom fallback paths
        win_fallback = Path(r"C:\Users\Bleed\Youtube DLP\YT-DLP\ffprobe.exe")
        if win_fallback.exists():
            return str(win_fallback)

        return self.ffprobe_path


@lru_cache
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
