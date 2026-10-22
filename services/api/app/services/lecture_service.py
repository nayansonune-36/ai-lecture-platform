"""Lecture management, resumable chunked upload, and authorization service."""

import re
import shutil
import uuid
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, forbidden
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.enums import JobStatus, JobType, LectureStatus, UserRole
from app.models.job import Job
from app.models.lecture import Lecture
from app.models.user import User
from app.schemas.lecture import LectureCreate, LectureUpdate
from app.services.job_queue import enqueue_background_job
from app.settings import get_settings

ALLOWED_EXTENSIONS = {"mp4", "mov", "mkv", "webm"}
CONTENT_RANGE_REGEX = re.compile(r"^bytes\s+(\d+)-(\d+)/(\d+|\*)$")


def validate_video_extension(filename: str) -> str:
    """Validate video filename and return normalized extension."""
    ext = Path(filename).suffix.lstrip(".").lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ApiError(
            status_code=400,
            code="invalid_file_type",
            message=f"Supported video formats are: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    return ext


def parse_content_range(header_val: str | None) -> tuple[int, int, int | None]:
    """Parse and validate Content-Range header (e.g., 'bytes 0-1048575/5242880')."""
    if not header_val:
        raise ApiError(
            status_code=400,
            code="missing_content_range",
            message="Content-Range header is required (e.g., 'bytes 0-1023/2048')",
        )

    match = CONTENT_RANGE_REGEX.match(header_val.strip())
    if not match:
        raise ApiError(
            status_code=400,
            code="invalid_content_range",
            message="Invalid Content-Range format. Expected 'bytes <start>-<end>/<total>'",
        )

    start = int(match.group(1))
    end = int(match.group(2))
    total_str = match.group(3)
    total = int(total_str) if total_str != "*" else None

    if start > end:
        raise ApiError(
            status_code=400,
            code="invalid_content_range",
            message="Content-Range start byte must be <= end byte",
        )

    if total is not None and end >= total:
        raise ApiError(
            status_code=400,
            code="invalid_content_range",
            message="Content-Range end byte must be strictly less than total size",
        )

    return start, end, total


async def create_lecture(
    db: AsyncSession,
    course_id: uuid.UUID,
    user: User,
    data: LectureCreate,
) -> tuple[Lecture, str]:
    """Create a lecture record and return the resumable upload URL."""
    course = await db.get(Course, course_id)
    if course is None:
        raise ApiError(status_code=404, code="course_not_found", message="Course not found")

    if user.role != UserRole.ADMIN and course.owner_id != user.id:
        raise forbidden("Only the course owner can create lectures", code="forbidden")

    ext = validate_video_extension(data.filename)

    # Determine position
    if data.position is None:
        stmt = select(func.coalesce(func.max(Lecture.position), -1) + 1).where(
            Lecture.course_id == course_id
        )
        pos = (await db.execute(stmt)).scalar_one()
    else:
        pos = data.position

    lecture_id = uuid.uuid4()
    original_path = f"lectures/{lecture_id}/original.{ext}"

    lecture = Lecture(
        id=lecture_id,
        course_id=course_id,
        title=data.title,
        description=data.description,
        position=pos,
        status=LectureStatus.UPLOADED,
        published=False,
        primary_language=data.primary_language,
        original_path=original_path,
        created_by=user.id,
    )
    db.add(lecture)
    await db.commit()
    await db.refresh(lecture)

    upload_url = f"/api/v1/lectures/{lecture.id}/upload"
    return lecture, upload_url


async def save_upload_chunk(
    db: AsyncSession,
    lecture_id: uuid.UUID,
    user: User,
    content_range_hdr: str | None,
    chunk_data: bytes,
) -> tuple[int, int, int | None]:
    """Write an uploaded chunk at the offset specified by Content-Range."""
    lecture = await db.get(Lecture, lecture_id)
    if lecture is None:
        raise ApiError(status_code=404, code="lecture_not_found", message="Lecture not found")

    course = await db.get(Course, lecture.course_id)
    if course is None or (user.role != UserRole.ADMIN and course.owner_id != user.id):
        raise forbidden("Only the course owner can upload lecture files", code="forbidden")

    start, end, total = parse_content_range(content_range_hdr)
    expected_size = end - start + 1
    if len(chunk_data) != expected_size:
        raise ApiError(
            status_code=400,
            code="chunk_size_mismatch",
            message=(
                f"Received {len(chunk_data)} bytes but "
                f"Content-Range specifies {expected_size} bytes"
            ),
        )

    settings = get_settings()
    max_size = settings.max_upload_size_bytes
    if total is not None and total > max_size:
        raise ApiError(
            status_code=413,
            code="file_too_large",
            message=f"File exceeds maximum allowed size of {max_size} bytes",
        )

    if end >= max_size:
        raise ApiError(
            status_code=413,
            code="file_too_large",
            message=f"Upload chunk exceeds maximum allowed size of {max_size} bytes",
        )

    file_path = settings.storage_root / lecture.original_path
    file_path.parent.mkdir(parents=True, exist_ok=True)

    mode = "r+b" if file_path.exists() else "wb+"
    with open(file_path, mode) as f:
        f.seek(start)
        f.write(chunk_data)
        f.flush()

    current_size = file_path.stat().st_size
    return len(chunk_data), current_size, total


async def complete_lecture_upload(
    db: AsyncSession,
    lecture_id: uuid.UUID,
    user: User,
) -> tuple[Lecture, Job]:
    """Mark upload complete, set status to processing, and queue transcode job."""
    lecture = await db.get(Lecture, lecture_id)
    if lecture is None:
        raise ApiError(status_code=404, code="lecture_not_found", message="Lecture not found")

    course = await db.get(Course, lecture.course_id)
    if course is None or (user.role != UserRole.ADMIN and course.owner_id != user.id):
        raise forbidden("Only the course owner can complete lecture upload", code="forbidden")

    settings = get_settings()
    file_path = settings.storage_root / lecture.original_path
    if not file_path.exists() or file_path.stat().st_size == 0:
        raise ApiError(
            status_code=400,
            code="upload_incomplete",
            message="No video data has been uploaded for this lecture",
        )

    lecture.status = LectureStatus.PROCESSING

    # Durable job record in database
    job = Job(
        lecture_id=lecture.id,
        type=JobType.TRANSCODE,
        status=JobStatus.QUEUED,
        payload={"original_path": lecture.original_path},
    )
    db.add(job)
    await db.commit()
    await db.refresh(lecture)
    await db.refresh(job)

    # Push to background worker queue in Redis
    await enqueue_background_job("transcode", lecture_id=str(lecture.id), job_id=str(job.id))

    return lecture, job


async def list_course_lectures(
    db: AsyncSession,
    course_id: uuid.UUID,
    user: User,
) -> list[Lecture]:
    """List lectures in a course. Students only see published + ready lectures."""
    course = await db.get(Course, course_id)
    if course is None:
        raise ApiError(status_code=404, code="course_not_found", message="Course not found")

    # Course owner, instructor, or admin sees all lectures
    if user.role == UserRole.ADMIN or course.owner_id == user.id:
        stmt = (
            select(Lecture)
            .where(Lecture.course_id == course_id)
            .order_by(Lecture.position.asc(), Lecture.created_at.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # Check enrollment
    enrollment_stmt = select(Enrollment).where(
        Enrollment.course_id == course_id,
        Enrollment.user_id == user.id,
    )
    enrollment = (await db.execute(enrollment_stmt)).scalar_one_or_none()
    if enrollment is None:
        raise forbidden("You are not enrolled in this course", code="forbidden")

    # Enrolled students only see published and ready lectures
    stmt = (
        select(Lecture)
        .where(
            Lecture.course_id == course_id,
            Lecture.published.is_(True),
            Lecture.status == LectureStatus.READY,
        )
        .order_by(Lecture.position.asc(), Lecture.created_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_lecture_detail(
    db: AsyncSession,
    lecture_id: uuid.UUID,
    user: User,
) -> Lecture:
    """Retrieve lecture detail enforcing can_view_lecture rules."""
    lecture = await db.get(Lecture, lecture_id)
    if lecture is None:
        raise ApiError(status_code=404, code="lecture_not_found", message="Lecture not found")

    course = await db.get(Course, lecture.course_id)
    if course is None:
        raise ApiError(status_code=404, code="course_not_found", message="Course not found")

    # Admin or owner
    if user.role == UserRole.ADMIN or course.owner_id == user.id:
        return lecture

    # Enrolled member
    enrollment_stmt = select(Enrollment).where(
        Enrollment.course_id == course.id,
        Enrollment.user_id == user.id,
    )
    enrollment = (await db.execute(enrollment_stmt)).scalar_one_or_none()
    if enrollment is None:
        raise forbidden("You are not enrolled in this course", code="forbidden")

    if not lecture.published or lecture.status != LectureStatus.READY:
        raise forbidden("This lecture is not yet available", code="forbidden")

    return lecture


async def update_lecture(
    db: AsyncSession,
    lecture_id: uuid.UUID,
    user: User,
    data: LectureUpdate,
) -> Lecture:
    """Update lecture metadata (owner or admin only)."""
    lecture = await db.get(Lecture, lecture_id)
    if lecture is None:
        raise ApiError(status_code=404, code="lecture_not_found", message="Lecture not found")

    course = await db.get(Course, lecture.course_id)
    if course is None or (user.role != UserRole.ADMIN and course.owner_id != user.id):
        raise forbidden("Only the course owner can edit this lecture", code="forbidden")

    if data.title is not None:
        lecture.title = data.title
    if data.description is not None:
        lecture.description = data.description
    if data.position is not None:
        lecture.position = data.position
    if data.published is not None:
        lecture.published = data.published
    if data.primary_language is not None:
        lecture.primary_language = data.primary_language

    await db.commit()
    await db.refresh(lecture)
    return lecture


async def delete_lecture(
    db: AsyncSession,
    lecture_id: uuid.UUID,
    user: User,
) -> None:
    """Delete a lecture and all its disk files (owner or admin only)."""
    lecture = await db.get(Lecture, lecture_id)
    if lecture is None:
        raise ApiError(status_code=404, code="lecture_not_found", message="Lecture not found")

    course = await db.get(Course, lecture.course_id)
    if course is None or (user.role != UserRole.ADMIN and course.owner_id != user.id):
        raise forbidden("Only the course owner can delete this lecture", code="forbidden")

    # Remove storage files
    settings = get_settings()
    lecture_dir = settings.storage_root / "lectures" / str(lecture.id)
    if lecture_dir.exists():
        shutil.rmtree(lecture_dir, ignore_errors=True)

    await db.execute(delete(Lecture).where(Lecture.id == lecture.id))
    await db.commit()


async def list_lecture_jobs(
    db: AsyncSession,
    lecture_id: uuid.UUID,
    user: User,
) -> list[Job]:
    """List background pipeline jobs for a lecture (owner or admin only)."""
    lecture = await db.get(Lecture, lecture_id)
    if lecture is None:
        raise ApiError(status_code=404, code="lecture_not_found", message="Lecture not found")

    course = await db.get(Course, lecture.course_id)
    if course is None or (user.role != UserRole.ADMIN and course.owner_id != user.id):
        raise forbidden("Only the course owner can view lecture jobs", code="forbidden")

    stmt = select(Job).where(Job.lecture_id == lecture_id).order_by(Job.created_at.asc())
    result = await db.execute(stmt)
    return list(result.scalars().all())
