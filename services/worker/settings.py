"""Configuration settings for the ARQ worker service."""

import shutil
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Worker settings loaded from environment or .env file."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres_dev_password@localhost:5432/lecture_platform"
    )
    redis_url: str = "redis://localhost:6379/0"
    storage_root: Path = Path("storage").resolve()
    max_upload_size_bytes: int = 8 * 1024 * 1024 * 1024  # 8 GB

    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"

    @property
    def resolved_storage_root(self) -> Path:
        """Resolve storage root to an absolute path."""
        if self.storage_root.is_absolute():
            return self.storage_root

        # Check candidate locations relative to repo root
        candidates = [
            Path.cwd() / self.storage_root,
            Path(__file__).resolve().parent.parent.parent / "storage",
            Path(__file__).resolve().parent.parent / "storage",
        ]
        for c in candidates:
            if c.exists():
                return c.resolve()
        return (Path(__file__).resolve().parent.parent.parent / "storage").resolve()

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
