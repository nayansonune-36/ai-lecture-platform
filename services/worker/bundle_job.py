"""Job execution and database persistence for offline bundle packaging."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bundler import build_bundle_zip
from db import get_db_session
from models import (
    Bundle,
    Chapter,
    Course,
    Job,
    JobStatus,
    JobType,
    Lecture,
    LectureRendition,
    TranscriptSegment,
)
from settings import get_settings

logger = logging.getLogger(__name__)


def _to_utc(dt: datetime | None) -> datetime | None:
    """Normalize datetime to UTC-aware datetime."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


async def cleanup_unused_bundles(
    session: AsyncSession,
    storage_root: Path,
    max_idle_days: int = 14,
) -> int:
    """Delete bundles whose creation date is older than max_idle_days."""
    cutoff = datetime.now(UTC) - timedelta(days=max_idle_days)
    stmt = select(Bundle).where(Bundle.created_at < cutoff)
    old_bundles = (await session.execute(stmt)).scalars().all()
    count = 0
    for b in old_bundles:
        bundle_file = (storage_root / b.path).resolve()
        if bundle_file.exists():
            try:
                bundle_file.unlink()
            except OSError:
                pass
        await session.delete(b)
        count += 1
    if count > 0:
        await session.commit()
        logger.info("Cleaned up %d bundles older than %d days", count, max_idle_days)
    return count


async def bundle_lecture_job(
    lecture_id: str,
    rendition: int,
    job_id: str | None = None,
    attempt: int = 1,
) -> dict[str, Any]:
    """Execute bundle creation, persist metadata to bundles table, and update job record."""
    if rendition not in (720, 480, 360):
        raise ValueError(f"Invalid rendition height: {rendition}. Must be 720, 480, or 360.")

    lecture_uuid = uuid.UUID(lecture_id)
    job_uuid = uuid.UUID(job_id) if job_id else None
    settings = get_settings()
    storage_root = settings.resolved_storage_root

    logger.info(
        "Starting bundle job for lecture %s (rendition=%dp, job_id=%s, attempt=%d)",
        lecture_id,
        rendition,
        job_id,
        attempt,
    )

    try:
        async with get_db_session() as session:
            # 1. Fetch lecture and course
            lecture = await session.get(Lecture, lecture_uuid)
            if lecture is None:
                raise ValueError(f"Lecture {lecture_id} not found in database")

            course_title = ""
            if lecture.course_id:
                course = await session.get(Course, lecture.course_id)
                if course:
                    course_title = course.title

            # 2. Verify rendition exists for this lecture
            rend_stmt = select(LectureRendition).where(
                LectureRendition.lecture_id == lecture_uuid,
                LectureRendition.height == rendition,
            )
            rendition_record = (await session.execute(rend_stmt)).scalar_one_or_none()
            if rendition_record is None:
                raise ValueError(
                    f"Rendition {rendition}p does not exist for lecture {lecture_id}"
                )

            # 3. Locate or update Job record
            target_job: Job | None = None
            if job_uuid:
                target_job = await session.get(Job, job_uuid)
            if target_job is None:
                q = (
                    select(Job)
                    .where(Job.lecture_id == lecture_uuid, Job.type == JobType.BUNDLE)
                    .order_by(Job.created_at.desc())
                )
                res = await session.execute(q)
                target_job = res.scalars().first()

            if target_job is None:
                target_job = Job(
                    lecture_id=lecture_uuid,
                    type=JobType.BUNDLE,
                    status=JobStatus.RUNNING,
                    attempts=attempt,
                    payload={"rendition": rendition},
                    started_at=datetime.now(UTC),
                )
                session.add(target_job)
                await session.flush()
                job_uuid = target_job.id
            else:
                job_uuid = target_job.id
                target_job.status = JobStatus.RUNNING
                target_job.attempts = attempt
                if not target_job.started_at:
                    target_job.started_at = datetime.now(UTC)

            # 4. Check idempotency: does a current bundle already exist?
            b_stmt = (
                select(Bundle)
                .where(Bundle.lecture_id == lecture_uuid, Bundle.rendition == rendition)
                .order_by(Bundle.version.desc())
            )
            existing_bundles = (await session.execute(b_stmt)).scalars().all()

            if existing_bundles:
                latest = existing_bundles[0]
                bundle_file = (storage_root / latest.path).resolve()
                lec_updated = _to_utc(lecture.updated_at)
                bundle_created = _to_utc(latest.created_at)

                # Check if bundle file exists and lecture has not changed since bundle creation
                is_current = (
                    bundle_file.is_file()
                    and lec_updated is not None
                    and bundle_created is not None
                    and lec_updated <= bundle_created
                )
                if is_current:
                    logger.info("Reusing existing bundle v%d at %s", latest.version, latest.path)
                    if target_job:
                        target_job.status = JobStatus.SUCCEEDED
                        target_job.finished_at = datetime.now(UTC)
                        target_job.payload = {
                            "rendition": rendition,
                            "bundle_id": str(latest.id),
                            "path": latest.path,
                            "version": latest.version,
                            "size_bytes": latest.size_bytes,
                            "sha256": latest.sha256,
                        }
                    await session.commit()
                    return {
                        "lecture_id": lecture_id,
                        "bundle_id": str(latest.id),
                        "rendition": rendition,
                        "version": latest.version,
                        "path": latest.path,
                        "size_bytes": latest.size_bytes,
                        "sha256": latest.sha256,
                        "reused": True,
                    }

                # Lecture has changed or bundle was missing
                next_version = latest.version + 1
            else:
                next_version = 1

            # 5. Delete bundles unused for 14 days
            await cleanup_unused_bundles(session, storage_root, max_idle_days=14)

            # 6. Fetch chapters and captions
            chap_stmt = (
                select(Chapter)
                .where(Chapter.lecture_id == lecture_uuid)
                .order_by(Chapter.idx)
            )
            chapters_db = (await session.execute(chap_stmt)).scalars().all()
            chapters_list = [
                {"start_ms": ch.start_ms, "title": ch.title, "summary": ch.summary}
                for ch in chapters_db
            ]

            seg_stmt = (
                select(TranscriptSegment)
                .where(TranscriptSegment.lecture_id == lecture_uuid)
                .order_by(TranscriptSegment.idx)
            )
            segments = (await session.execute(seg_stmt)).scalars().all()
            captions_vtt: str | None = None
            if segments:
                vtt_lines = ["WEBVTT", ""]
                for seg in segments:
                    s_sec = seg.start_ms / 1000.0
                    e_sec = seg.end_ms / 1000.0
                    s_h, s_m, s_s = int(s_sec // 3600), int((s_sec % 3600) // 60), s_sec % 60
                    e_h, e_m, e_s = int(e_sec // 3600), int((e_sec % 3600) // 60), e_sec % 60
                    s_str = f"{s_h:02d}:{s_m:02d}:{s_s:06.3f}"
                    e_str = f"{e_h:02d}:{e_m:02d}:{e_s:06.3f}"
                    vtt_lines.append(f"{s_str} --> {e_str}")
                    vtt_lines.append(seg.text)
                    vtt_lines.append("")
                captions_vtt = "\n".join(vtt_lines)

            # 7. Build bundle archive
            bundle_result = build_bundle_zip(
                storage_root=storage_root,
                lecture_id=lecture_uuid,
                rendition=rendition,
                version=next_version,
                lecture_title=lecture.title,
                course_title=course_title,
                duration_ms=lecture.duration_ms,
                chapters=chapters_list,
                captions_vtt=captions_vtt,
                bitrate_kbps=rendition_record.bitrate_kbps,
            )

            # 8. Record bundle in database
            bundle_record = Bundle(
                id=uuid.uuid4(),
                lecture_id=lecture_uuid,
                rendition=rendition,
                version=next_version,
                path=bundle_result["path"],
                size_bytes=bundle_result["size_bytes"],
                sha256=bundle_result["sha256"],
                created_at=datetime.now(UTC),
            )
            session.add(bundle_record)

            # 9. Update Job record
            if target_job:
                target_job.status = JobStatus.SUCCEEDED
                target_job.finished_at = datetime.now(UTC)
                target_job.payload = {
                    "rendition": rendition,
                    "bundle_id": str(bundle_record.id),
                    "path": bundle_record.path,
                    "version": next_version,
                    "size_bytes": bundle_result["size_bytes"],
                    "sha256": bundle_result["sha256"],
                }

            await session.commit()

            return {
                "lecture_id": lecture_id,
                "bundle_id": str(bundle_record.id),
                "rendition": rendition,
                "version": next_version,
                "path": bundle_record.path,
                "size_bytes": bundle_record.size_bytes,
                "sha256": bundle_record.sha256,
                "reused": False,
            }

    except Exception as exc:
        logger.exception("Bundle job failed for lecture %s: %s", lecture_id, exc)
        await _record_failure(job_uuid, attempt, str(exc))
        raise


async def _record_failure(
    job_uuid: uuid.UUID | None,
    attempt: int,
    error_message: str,
) -> None:
    """Record bundle job failure in database."""
    async with get_db_session() as session:
        if job_uuid:
            job = await session.get(Job, job_uuid)
            if job:
                job.attempts = attempt
                job.error = error_message
                if attempt >= 3:
                    job.status = JobStatus.FAILED
                    job.finished_at = datetime.now(UTC)
        await session.commit()
