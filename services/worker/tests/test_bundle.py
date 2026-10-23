"""Tests for offline bundle packaging, manifest validation, ffprobe playback, and idempotency."""

import hashlib
import json
import subprocess
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bundle_job import bundle_lecture_job, cleanup_unused_bundles
from models import Bundle, Course, Lecture, LectureRendition, LectureStatus
from settings import get_settings
from transcoder import run_transcode_pipeline


@pytest.fixture
async def sample_transcoded_lecture(
    db_session: AsyncSession,
    synthetic_video_720p: Path,
    ffmpeg_bin: str,
    ffprobe_bin: str,
) -> tuple[Lecture, Course]:
    """Create a course, lecture, and transcode media into the worker storage root."""
    settings = get_settings()
    storage_root = settings.resolved_storage_root

    course = Course(
        id=uuid.uuid4(),
        code="CS501",
        title="High Performance Computing",
        description="Parallel systems course",
    )
    db_session.add(course)
    await db_session.flush()

    lecture_id = uuid.uuid4()
    hls_dir = storage_root / "lectures" / str(lecture_id) / "hls"
    hls_dir.mkdir(parents=True, exist_ok=True)

    transcode_res = await run_transcode_pipeline(
        input_path=synthetic_video_720p,
        output_hls_dir=hls_dir,
        ffmpeg_binary=ffmpeg_bin,
        ffprobe_binary=ffprobe_bin,
    )

    lecture = Lecture(
        id=lecture_id,
        course_id=course.id,
        title="GPU Architectures",
        original_path=f"lectures/{lecture_id}/original.mp4",
        hls_master_path=f"lectures/{lecture_id}/hls/master.m3u8",
        poster_path=f"lectures/{lecture_id}/hls/poster.jpg",
        duration_ms=transcode_res.duration_ms,
        status=LectureStatus.READY,
        published=True,
        created_by=uuid.uuid4(),
        created_at=datetime.now(UTC) - timedelta(minutes=10),
        updated_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    db_session.add(lecture)
    await db_session.flush()

    for r in transcode_res.renditions:
        rendition_row = LectureRendition(
            lecture_id=lecture.id,
            height=r.height,
            bitrate_kbps=r.bitrate_kbps,
            playlist_path=f"lectures/{lecture.id}/hls/{r.height}p/index.m3u8",
            size_bytes=r.size_bytes,
        )
        db_session.add(rendition_row)

    await db_session.commit()
    await db_session.refresh(lecture)
    return lecture, course


@pytest.mark.asyncio
async def test_bundle_contents_and_manifest_hashes_match(
    sample_transcoded_lecture: tuple[Lecture, Course],
    db_session: AsyncSession,
) -> None:
    """Verify bundle zip structure and that manifest file entries match actual zip contents."""
    lecture, course = sample_transcoded_lecture
    settings = get_settings()
    storage_root = settings.resolved_storage_root

    result = await bundle_lecture_job(lecture_id=str(lecture.id), rendition=720)
    assert result["version"] == 1
    assert result["reused"] is False

    zip_path = storage_root / result["path"]
    assert zip_path.is_file()

    # Open zip and check required files
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = set(zf.namelist())
        assert "manifest.json" in namelist
        assert "hls/master.m3u8" in namelist
        assert "hls/media.m3u8" in namelist
        assert "hls/init.mp4" in namelist
        assert "poster.jpg" in namelist
        assert "captions.vtt" in namelist
        assert "chapters.json" in namelist

        # At least one segment
        segments = [n for n in namelist if n.startswith("hls/segment_")]
        assert len(segments) >= 1

        # Check manifest
        manifest_raw = zf.read("manifest.json")
        manifest = json.loads(manifest_raw.decode("utf-8"))

        assert manifest["schema_version"] == 1
        assert manifest["lecture_id"] == str(lecture.id)
        assert manifest["title"] == lecture.title
        assert manifest["course_title"] == course.title
        assert manifest["duration_ms"] == lecture.duration_ms
        assert manifest["rendition"] == 720
        assert manifest["ai_index"] is None

        # Verify every file in manifest matches actual bytes
        manifest_paths = set()
        for f in manifest["files"]:
            manifest_paths.add(f["path"])
            assert f["path"] in namelist
            file_bytes = zf.read(f["path"])
            assert len(file_bytes) == f["size"]
            assert hashlib.sha256(file_bytes).hexdigest() == f["sha256"]

        # All files in zip (except manifest.json) must be in manifest
        non_manifest_names = {n for n in namelist if n != "manifest.json"}
        assert non_manifest_names == manifest_paths

    # Verify DB record
    stmt = select(Bundle).where(Bundle.lecture_id == lecture.id, Bundle.rendition == 720)
    bundle_row = (await db_session.execute(stmt)).scalar_one()
    assert bundle_row.size_bytes == zip_path.stat().st_size
    assert bundle_row.sha256 == result["sha256"]


@pytest.mark.asyncio
async def test_bundle_playlist_paths_relative_and_play_with_ffprobe(
    sample_transcoded_lecture: tuple[Lecture, Course],
    tmp_path: Path,
    ffprobe_bin: str,
) -> None:
    """Verify playlist paths are relative and playable by ffprobe."""
    lecture, _ = sample_transcoded_lecture
    settings = get_settings()
    storage_root = settings.resolved_storage_root

    result = await bundle_lecture_job(lecture_id=str(lecture.id), rendition=720)
    zip_path = storage_root / result["path"]

    extract_dir = tmp_path / "extracted_bundle"
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    # Check relative paths in hls/master.m3u8
    master_content = (extract_dir / "hls" / "master.m3u8").read_text(encoding="utf-8")
    assert "media.m3u8" in master_content
    assert "/" not in master_content.split("media.m3u8")[0].splitlines()[-1]

    # Check relative paths in hls/media.m3u8
    media_content = (extract_dir / "hls" / "media.m3u8").read_text(encoding="utf-8")
    assert '#EXT-X-MAP:URI="init.mp4"' in media_content
    for line in media_content.splitlines():
        if line.endswith(".m4s"):
            assert "/" not in line
            assert "\\" not in line

    # Run ffprobe on master.m3u8 inside extracted bundle
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(extract_dir / "hls" / "master.m3u8"),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    duration_probed = float(res.stdout.strip())
    assert duration_probed >= 3.0


@pytest.mark.asyncio
async def test_bundle_idempotency_and_version_bumping(
    sample_transcoded_lecture: tuple[Lecture, Course],
    db_session: AsyncSession,
) -> None:
    """Verify rerun reuses current bundle and bumping occurs only when lecture updates."""
    lecture, _ = sample_transcoded_lecture

    # 1. First run creates version 1
    res1 = await bundle_lecture_job(lecture_id=str(lecture.id), rendition=720)
    assert res1["version"] == 1
    assert res1["reused"] is False

    # 2. Rerun immediately reuses version 1 without duplicating rows
    res2 = await bundle_lecture_job(lecture_id=str(lecture.id), rendition=720)
    assert res2["version"] == 1
    assert res2["reused"] is True
    assert res2["bundle_id"] == res1["bundle_id"]

    stmt = select(Bundle).where(Bundle.lecture_id == lecture.id, Bundle.rendition == 720)
    bundles = (await db_session.execute(stmt)).scalars().all()
    assert len(bundles) == 1

    # 3. Simulate lecture change / reprocessing
    lecture.updated_at = datetime.now(UTC) + timedelta(seconds=2)
    await db_session.commit()

    # 4. Running again bumps version to 2
    res3 = await bundle_lecture_job(lecture_id=str(lecture.id), rendition=720)
    assert res3["version"] == 2
    assert res3["reused"] is False

    bundles_after = (await db_session.execute(stmt)).scalars().all()
    assert len(bundles_after) == 2


@pytest.mark.asyncio
async def test_cleanup_unused_bundles(
    sample_transcoded_lecture: tuple[Lecture, Course],
    db_session: AsyncSession,
) -> None:
    """Verify cleanup deletes bundle rows and zip files older than 14 days."""
    lecture, _ = sample_transcoded_lecture
    settings = get_settings()
    storage_root = settings.resolved_storage_root

    result = await bundle_lecture_job(lecture_id=str(lecture.id), rendition=720)
    zip_path = storage_root / result["path"]
    assert zip_path.is_file()

    # Age the bundle past 14 days
    stmt = select(Bundle).where(Bundle.id == uuid.UUID(result["bundle_id"]))
    bundle_row = (await db_session.execute(stmt)).scalar_one()
    bundle_row.created_at = datetime.now(UTC) - timedelta(days=15)
    await db_session.commit()

    # Run cleanup
    cleaned = await cleanup_unused_bundles(db_session, storage_root, max_idle_days=14)
    assert cleaned == 1
    assert not zip_path.exists()

    # Ensure DB record is removed
    deleted_row = (await db_session.execute(stmt)).scalar_one_or_none()
    assert deleted_row is None
