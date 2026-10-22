"""Job execution and database persistence for lecture transcoding."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select

from db import get_db_session
from models import Job, JobStatus, JobType, Lecture, LectureRendition, LectureStatus
from settings import get_settings
from transcoder import run_transcode_pipeline

logger = logging.getLogger(__name__)


async def transcode_lecture_job(
    lecture_id: str,
    job_id: str | None = None,
    attempt: int = 1,
    ffmpeg_binary: str | None = None,
    ffprobe_binary: str | None = None,
) -> dict[str, Any]:
    """Execute transcode job, update lecture and renditions, record job status."""
    lecture_uuid = uuid.UUID(lecture_id)
    job_uuid = uuid.UUID(job_id) if job_id else None
    settings = get_settings()
    storage_root = settings.resolved_storage_root

    logger.info(
        "Starting transcode job for lecture %s (job_id=%s, attempt=%d)",
        lecture_id,
        job_id,
        attempt,
    )

    # 1. Update job to processing in database
    original_rel_path: str = ""
    async with get_db_session() as session:
        lecture = await session.get(Lecture, lecture_uuid)
        if lecture is None:
            raise ValueError(f"Lecture {lecture_id} not found in database")

        original_rel_path = lecture.original_path
        lecture.status = LectureStatus.PROCESSING

        # Locate or create Job record
        target_job: Job | None = None
        if job_uuid:
            target_job = await session.get(Job, job_uuid)

        if target_job is None:
            q = (
                select(Job)
                .where(Job.lecture_id == lecture_uuid, Job.type == JobType.TRANSCODE)
                .order_by(Job.created_at.desc())
            )
            res = await session.execute(q)
            target_job = res.scalars().first()

        if target_job is None:
            target_job = Job(
                lecture_id=lecture_uuid,
                type=JobType.TRANSCODE,
                status=JobStatus.PROCESSING,
                attempts=attempt,
                started_at=datetime.now(UTC),
            )
            session.add(target_job)
            await session.flush()
            job_uuid = target_job.id
        else:
            job_uuid = target_job.id
            target_job.status = JobStatus.PROCESSING
            target_job.attempts = attempt
            if not target_job.started_at:
                target_job.started_at = datetime.now(UTC)

        await session.commit()

    # 2. Resolve input and output paths
    input_path = (storage_root / original_rel_path).resolve()
    if not input_path.exists():
        err_msg = f"Original video file not found at {input_path}"
        await _record_failure(lecture_uuid, job_uuid, attempt, err_msg)
        raise FileNotFoundError(err_msg)

    output_hls_dir = (storage_root / "lectures" / str(lecture_id) / "hls").resolve()

    # 3. Run transcoding pipeline
    try:
        pipeline_result = await run_transcode_pipeline(
            input_path=input_path,
            output_hls_dir=output_hls_dir,
            ffmpeg_binary=ffmpeg_binary,
            ffprobe_binary=ffprobe_binary,
        )
    except Exception as exc:
        logger.exception("Transcoding failed for lecture %s: %s", lecture_id, exc)
        await _record_failure(lecture_uuid, job_uuid, attempt, str(exc))
        raise

    # 4. Success: persist outputs and update status to ready
    hls_master_rel = f"lectures/{lecture_id}/hls/master.m3u8"
    poster_rel = f"lectures/{lecture_id}/hls/poster.jpg"

    async with get_db_session() as session:
        lecture = await session.get(Lecture, lecture_uuid)
        if lecture:
            lecture.duration_ms = pipeline_result.duration_ms
            lecture.hls_master_path = hls_master_rel
            lecture.poster_path = poster_rel
            lecture.status = LectureStatus.READY
            lecture.updated_at = datetime.now(UTC)

        # Idempotently delete any existing renditions for this lecture
        await session.execute(
            delete(LectureRendition).where(LectureRendition.lecture_id == lecture_uuid)
        )

        # Insert new renditions
        for r in pipeline_result.renditions:
            rendition_rel = f"lectures/{lecture_id}/hls/{r.height}p/index.m3u8"
            rendition = LectureRendition(
                lecture_id=lecture_uuid,
                height=r.height,
                bitrate_kbps=r.bitrate_kbps,
                playlist_path=rendition_rel,
                size_bytes=r.size_bytes,
            )
            session.add(rendition)

        # Update Job row
        if job_uuid:
            job = await session.get(Job, job_uuid)
            if job:
                job.status = JobStatus.COMPLETED
                job.attempts = attempt
                job.error = None
                job.finished_at = datetime.now(UTC)

        await session.commit()

    logger.info(
        "Successfully transcoded lecture %s: %d renditions, duration=%d ms",
        lecture_id,
        len(pipeline_result.renditions),
        pipeline_result.duration_ms,
    )

    return {
        "lecture_id": lecture_id,
        "job_id": str(job_uuid) if job_uuid else None,
        "duration_ms": pipeline_result.duration_ms,
        "renditions": [
            {
                "height": r.height,
                "bitrate_kbps": r.bitrate_kbps,
                "size_bytes": r.size_bytes,
                "playlist_path": f"lectures/{lecture_id}/hls/{r.height}p/index.m3u8",
            }
            for r in pipeline_result.renditions
        ],
        "hls_master_path": hls_master_rel,
        "poster_path": poster_rel,
        "thumbnail_count": len(pipeline_result.thumbnails),
    }


async def _record_failure(
    lecture_uuid: uuid.UUID,
    job_uuid: uuid.UUID | None,
    attempt: int,
    error_message: str,
) -> None:
    """Record job attempt failure in database and mark failed if attempts >= 3."""
    async with get_db_session() as session:
        if job_uuid:
            job = await session.get(Job, job_uuid)
            if job:
                job.attempts = attempt
                job.error = error_message
                if attempt >= 3:
                    job.status = JobStatus.FAILED
                    job.finished_at = datetime.now(UTC)

        if attempt >= 3:
            lecture = await session.get(Lecture, lecture_uuid)
            if lecture:
                lecture.status = LectureStatus.FAILED
                lecture.updated_at = datetime.now(UTC)

        await session.commit()
