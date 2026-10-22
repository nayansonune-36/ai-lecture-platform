"""Pytest configuration and shared fixtures for worker tests."""

import subprocess
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db import Base, set_engine_and_factory
from settings import get_settings

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def ffmpeg_bin() -> str:
    """Return verified ffmpeg binary path."""
    return get_settings().get_ffmpeg_binary()


@pytest.fixture(scope="session")
def ffprobe_bin() -> str:
    """Return verified ffprobe binary path."""
    return get_settings().get_ffprobe_binary()


@pytest.fixture(scope="session")
def synthetic_video_720p(tmp_path_factory: pytest.TempPathFactory, ffmpeg_bin: str) -> Path:
    """Generate a 4-second 720p test video with audio."""
    tmp_dir = tmp_path_factory.mktemp("media")
    video_path = tmp_dir / "sample_720p.mp4"
    cmd = [
        ffmpeg_bin,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=4:size=1280x720:rate=30",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=1000:duration=4",
        "-pix_fmt",
        "yuv420p",
        str(video_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return video_path


@pytest.fixture(scope="session")
def synthetic_video_480p(tmp_path_factory: pytest.TempPathFactory, ffmpeg_bin: str) -> Path:
    """Generate a 2-second 480p test video without audio."""
    tmp_dir = tmp_path_factory.mktemp("media")
    video_path = tmp_dir / "sample_480p.mp4"
    cmd = [
        ffmpeg_bin,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=2:size=854x480:rate=30",
        "-pix_fmt",
        "yuv420p",
        str(video_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return video_path


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated in-memory SQLite database session and configure db module."""
    engine = create_async_engine(
        TEST_DB_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Set engine and factory in db module
    set_engine_and_factory(engine, session_factory)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
