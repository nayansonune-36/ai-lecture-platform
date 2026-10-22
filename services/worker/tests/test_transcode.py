"""Tests for ffprobe probing, FFmpeg HLS fMP4 transcoding, idempotency, and retries."""

import argparse
import shutil
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cli import _main_async
from models import Job, JobStatus, JobType, Lecture, LectureRendition, LectureStatus
from settings import get_settings
from transcode_job import transcode_lecture_job
from transcoder import probe_video, run_transcode_pipeline, select_renditions


@pytest.mark.asyncio
async def test_probe_video_metadata(
    synthetic_video_720p: Path,
    synthetic_video_480p: Path,
    ffprobe_bin: str,
) -> None:
    """Verify ffprobe correctly extracts duration, streams, and technical attributes."""
    meta_720 = await probe_video(synthetic_video_720p, ffprobe_binary=ffprobe_bin)
    assert meta_720.video.width == 1280
    assert meta_720.video.height == 720
    assert meta_720.duration_s >= 3.5
    assert meta_720.duration_ms >= 3500
    assert meta_720.has_audio is True
    assert meta_720.audio is not None
    assert meta_720.audio.codec_name == "aac"

    meta_480 = await probe_video(synthetic_video_480p, ffprobe_binary=ffprobe_bin)
    assert meta_480.video.height == 480
    assert meta_480.duration_s >= 1.5
    assert meta_480.has_audio is False
    assert meta_480.audio is None


def test_select_renditions_skip_larger_than_source() -> None:
    """Verify renditions larger than source are skipped."""
    # 1080p source -> produces 720p, 480p, 360p
    r_1080 = select_renditions(1080)
    assert [r.height for r in r_1080] == [720, 480, 360]

    # 720p source -> produces 720p, 480p, 360p
    r_720 = select_renditions(720)
    assert [r.height for r in r_720] == [720, 480, 360]

    # 480p source -> skips 720p, produces 480p and 360p
    r_480 = select_renditions(480)
    assert [r.height for r in r_480] == [480, 360]

    # 360p source -> skips 720p and 480p, produces 360p
    r_360 = select_renditions(360)
    assert [r.height for r in r_360] == [360]

    # 240p source -> fallback to source resolution
    r_240 = select_renditions(240)
    assert [r.height for r in r_240] == [240]


@pytest.mark.asyncio
async def test_transcode_pipeline_fmp4_output(
    synthetic_video_720p: Path,
    tmp_path: Path,
    ffmpeg_bin: str,
    ffprobe_bin: str,
) -> None:
    """Verify full transcoding pipeline produces valid fMP4 HLS, master, poster, and thumbnails."""
    out_dir = tmp_path / "hls_test"
    result = await run_transcode_pipeline(
        input_path=synthetic_video_720p,
        output_hls_dir=out_dir,
        ffmpeg_binary=ffmpeg_bin,
        ffprobe_binary=ffprobe_bin,
    )

    assert result.duration_ms >= 3500
    assert len(result.renditions) == 3
    assert result.master_playlist.exists()
    assert result.poster_image.exists()

    master_content = result.master_playlist.read_text(encoding="utf-8")
    assert "#EXTM3U" in master_content
    assert "#EXT-X-VERSION:7" in master_content
    assert "720p/index.m3u8" in master_content
    assert "480p/index.m3u8" in master_content
    assert "360p/index.m3u8" in master_content

    # Check each rendition has fMP4 init.mp4 and segments
    for r in result.renditions:
        rend_dir = out_dir / f"{r.height}p"
        assert (rend_dir / "init.mp4").exists()
        assert (rend_dir / "index.m3u8").exists()
        segments = list(rend_dir.glob("segment_*.m4s"))
        assert len(segments) >= 1
        assert r.size_bytes > 0

    # Check thumbnails and VTT
    thumb_dir = out_dir / "thumbnails"
    assert (thumb_dir / "thumbnails.vtt").exists()
    vtt_content = (thumb_dir / "thumbnails.vtt").read_text(encoding="utf-8")
    assert "WEBVTT" in vtt_content
    assert len(result.thumbnails) >= 1


@pytest.mark.asyncio
async def test_transcode_job_success_and_idempotency(
    synthetic_video_720p: Path,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ffmpeg_bin: str,
    ffprobe_bin: str,
) -> None:
    """Verify transcode job execution, database updates, and idempotency on re-run."""
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    monkeypatch.setattr(get_settings(), "storage_root", storage_root)

    lecture_id = uuid.uuid4()
    course_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # Place original video in simulated storage
    lecture_dir = storage_root / "lectures" / str(lecture_id)
    lecture_dir.mkdir(parents=True)
    orig_file = lecture_dir / "original.mp4"
    shutil.copyfile(synthetic_video_720p, orig_file)

    orig_rel_path = f"lectures/{lecture_id}/original.mp4"

    # Insert Lecture and Job records
    lecture = Lecture(
        id=lecture_id,
        course_id=course_id,
        title="Intro to Computing",
        original_path=orig_rel_path,
        status=LectureStatus.PROCESSING,
        created_by=user_id,
    )
    job = Job(
        lecture_id=lecture_id,
        type=JobType.TRANSCODE,
        status=JobStatus.QUEUED,
        attempts=0,
    )
    db_session.add(lecture)
    db_session.add(job)
    await db_session.commit()

    # 1. First execution (attempt 1)
    res1 = await transcode_lecture_job(
        lecture_id=str(lecture_id),
        job_id=str(job.id),
        attempt=1,
        ffmpeg_binary=ffmpeg_bin,
        ffprobe_binary=ffprobe_bin,
    )

    assert res1["duration_ms"] >= 3500
    assert len(res1["renditions"]) == 3

    # Check updated database state
    await db_session.refresh(lecture)
    await db_session.refresh(job)

    assert lecture.status == LectureStatus.READY
    assert lecture.duration_ms is not None
    assert lecture.duration_ms >= 3500
    assert lecture.hls_master_path == f"lectures/{lecture_id}/hls/master.m3u8"
    assert lecture.poster_path == f"lectures/{lecture_id}/hls/poster.jpg"

    assert job.status == JobStatus.COMPLETED
    assert job.attempts == 1
    assert job.error is None
    assert job.finished_at is not None

    renditions_q = await db_session.execute(
        select(LectureRendition).where(LectureRendition.lecture_id == lecture_id)
    )
    renditions = list(renditions_q.scalars().all())
    assert len(renditions) == 3
    heights = {r.height for r in renditions}
    assert heights == {720, 480, 360}

    # 2. Idempotency re-run (same lecture, simulating reprocessing or worker restart)
    res2 = await transcode_lecture_job(
        lecture_id=str(lecture_id),
        job_id=str(job.id),
        attempt=2,
        ffmpeg_binary=ffmpeg_bin,
        ffprobe_binary=ffprobe_bin,
    )

    assert res2["duration_ms"] == res1["duration_ms"]

    # Verify no duplicate renditions were inserted
    renditions_q2 = await db_session.execute(
        select(LectureRendition).where(LectureRendition.lecture_id == lecture_id)
    )
    renditions2 = list(renditions_q2.scalars().all())
    assert len(renditions2) == 3  # Still exactly 3 rows, not 6


@pytest.mark.asyncio
async def test_transcode_job_retry_and_failure(
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ffmpeg_bin: str,
    ffprobe_bin: str,
) -> None:
    """Verify attempt tracking and permanent failure handling after 3 retries."""
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    monkeypatch.setattr(get_settings(), "storage_root", storage_root)

    lecture_id = uuid.uuid4()
    course_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # Original path does not exist
    orig_rel_path = f"lectures/{lecture_id}/missing_file.mp4"

    lecture = Lecture(
        id=lecture_id,
        course_id=course_id,
        title="Missing Lecture",
        original_path=orig_rel_path,
        status=LectureStatus.PROCESSING,
        created_by=user_id,
    )
    job = Job(
        lecture_id=lecture_id,
        type=JobType.TRANSCODE,
        status=JobStatus.QUEUED,
        attempts=0,
    )
    db_session.add(lecture)
    db_session.add(job)
    await db_session.commit()

    # Attempt 1: Should fail, but not mark permanent failure yet
    with pytest.raises(FileNotFoundError):
        await transcode_lecture_job(
            lecture_id=str(lecture_id),
            job_id=str(job.id),
            attempt=1,
            ffmpeg_binary=ffmpeg_bin,
            ffprobe_binary=ffprobe_bin,
        )

    await db_session.refresh(job)
    await db_session.refresh(lecture)
    assert job.attempts == 1
    assert job.status == JobStatus.PROCESSING
    assert job.error is not None
    assert lecture.status == LectureStatus.PROCESSING

    # Attempt 2: Still failing
    with pytest.raises(FileNotFoundError):
        await transcode_lecture_job(
            lecture_id=str(lecture_id),
            job_id=str(job.id),
            attempt=2,
            ffmpeg_binary=ffmpeg_bin,
            ffprobe_binary=ffprobe_bin,
        )

    await db_session.refresh(job)
    await db_session.refresh(lecture)
    assert job.attempts == 2
    assert job.status == JobStatus.PROCESSING

    # Attempt 3: Final attempt -> marks job and lecture as FAILED
    with pytest.raises(FileNotFoundError):
        await transcode_lecture_job(
            lecture_id=str(lecture_id),
            job_id=str(job.id),
            attempt=3,
            ffmpeg_binary=ffmpeg_bin,
            ffprobe_binary=ffprobe_bin,
        )

    res_job = await db_session.execute(
        select(Job).where(Job.id == job.id).execution_options(populate_existing=True)
    )
    failed_job = res_job.scalar_one()

    res_lec = await db_session.execute(
        select(Lecture).where(Lecture.id == lecture_id).execution_options(populate_existing=True)
    )
    failed_lecture = res_lec.scalar_one()

    assert failed_job.attempts == 3
    assert failed_job.status == JobStatus.FAILED
    assert failed_job.finished_at is not None
    assert failed_lecture.status == LectureStatus.FAILED


@pytest.mark.asyncio
async def test_cli_execution_standalone(
    synthetic_video_480p: Path,
    tmp_path: Path,
    ffmpeg_bin: str,
    ffprobe_bin: str,
) -> None:
    """Verify CLI executes standalone transcoding pipeline without database."""
    out_dir = tmp_path / "cli_hls"
    args = argparse.Namespace(
        input_file=str(synthetic_video_480p),
        output_dir=str(out_dir),
        lecture_id=None,
        job_id=None,
        skip_db=True,
        ffmpeg=ffmpeg_bin,
        ffprobe=ffprobe_bin,
    )

    exit_code = await _main_async(args)
    assert exit_code == 0
    assert (out_dir / "master.m3u8").exists()
    assert (out_dir / "poster.jpg").exists()
    assert (out_dir / "480p" / "index.m3u8").exists()
    assert (out_dir / "360p" / "index.m3u8").exists()
    # 720p was skipped because source is 480p
    assert not (out_dir / "720p").exists()
