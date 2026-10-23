"""Offline bundle estimation, queuing, and download services."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.models.bundle import Bundle
from app.models.enums import JobStatus, JobType, LectureStatus
from app.models.job import Job
from app.models.lecture import LectureRendition
from app.models.user import User
from app.schemas.bundle import (
    OfflineBundleRequest,
    OfflineBundleResponse,
    OfflineEstimateResponse,
)
from app.services.job_queue import enqueue_background_job
from app.services.lecture_service import get_lecture_detail
from app.services.playback_service import generate_signed_media_url
from app.settings import get_settings


async def get_offline_estimate(
    db: AsyncSession,
    lecture_id: uuid.UUID,
    rendition: int,
    user: User,
) -> OfflineEstimateResponse:
    """Calculate approximate download size for a lecture rendition."""
    if rendition not in (720, 480, 360):
        raise ApiError(
            status_code=400,
            code="invalid_rendition",
            message=f"Invalid rendition height: {rendition}. Must be 720, 480, or 360.",
        )

    lecture = await get_lecture_detail(db, lecture_id, user)

    # 1. Check if a built bundle already exists
    stmt = (
        select(Bundle)
        .where(Bundle.lecture_id == lecture_id, Bundle.rendition == rendition)
        .order_by(Bundle.version.desc())
    )
    bundle = (await db.execute(stmt)).scalars().first()
    if bundle:
        return OfflineEstimateResponse(
            lecture_id=lecture.id,
            rendition=rendition,
            estimated_size_bytes=bundle.size_bytes,
        )

    # 2. Check rendition in database
    r_stmt = select(LectureRendition).where(
        LectureRendition.lecture_id == lecture_id,
        LectureRendition.height == rendition,
    )
    rendition_record = (await db.execute(r_stmt)).scalar_one_or_none()
    if rendition_record is None:
        raise ApiError(
            status_code=404,
            code="rendition_not_found",
            message=f"Rendition {rendition}p not found for lecture {lecture_id}",
        )

    if rendition_record.size_bytes and rendition_record.size_bytes > 0:
        estimated_size = rendition_record.size_bytes + 50_000  # include metadata/poster overhead
    else:
        duration_s = (lecture.duration_ms or 0) / 1000.0
        bitrate_kbps = rendition_record.bitrate_kbps or 1200
        estimated_size = int((bitrate_kbps * 1000 / 8) * duration_s) + 50_000

    return OfflineEstimateResponse(
        lecture_id=lecture.id,
        rendition=rendition,
        estimated_size_bytes=estimated_size,
    )


async def request_offline_bundle(
    db: AsyncSession,
    lecture_id: uuid.UUID,
    payload: OfflineBundleRequest,
    user: User,
) -> OfflineBundleResponse:
    """Request offline bundle packaging or return existing bundle download URL."""
    rendition = payload.rendition
    if rendition not in (720, 480, 360):
        raise ApiError(
            status_code=400,
            code="invalid_rendition",
            message=f"Invalid rendition height: {rendition}. Must be 720, 480, or 360.",
        )

    lecture = await get_lecture_detail(db, lecture_id, user)
    if lecture.status != LectureStatus.READY:
        raise ApiError(
            status_code=409,
            code="lecture_not_ready",
            message=f"Lecture is not ready for offline bundling (status: {lecture.status.value})",
        )

    r_stmt = select(LectureRendition).where(
        LectureRendition.lecture_id == lecture_id,
        LectureRendition.height == rendition,
    )
    rendition_record = (await db.execute(r_stmt)).scalar_one_or_none()
    if rendition_record is None:
        raise ApiError(
            status_code=404,
            code="rendition_not_found",
            message=f"Rendition {rendition}p not found for lecture {lecture_id}",
        )

    settings = get_settings()
    storage_root = settings.resolved_storage_root

    # Check if a bundle exists and is up-to-date
    b_stmt = (
        select(Bundle)
        .where(Bundle.lecture_id == lecture_id, Bundle.rendition == rendition)
        .order_by(Bundle.version.desc())
    )
    bundle = (await db.execute(b_stmt)).scalars().first()

    if bundle:
        bundle_file = (storage_root / bundle.path).resolve()
        lec_updated = lecture.updated_at
        if lec_updated.tzinfo is None:
            lec_updated = lec_updated.replace(tzinfo=UTC)
        bundle_created = bundle.created_at
        if bundle_created.tzinfo is None:
            bundle_created = bundle_created.replace(tzinfo=UTC)

        if bundle_file.is_file() and lec_updated <= bundle_created:
            # Bundle exists and is up to date; create or use succeeded job
            job = Job(
                lecture_id=lecture.id,
                type=JobType.BUNDLE,
                status=JobStatus.SUCCEEDED,
                payload={"rendition": rendition, "bundle_id": str(bundle.id)},
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)

            expires_at = datetime.now(UTC) + timedelta(minutes=settings.media_url_expire_minutes)
            signed_url = generate_signed_media_url(
                path=f"/media/{bundle.path}",
                user_id=user.id,
                expires_at_unix=int(expires_at.timestamp()),
                signing_key=settings.media_signing_key,
            )

            return OfflineBundleResponse(
                job_id=job.id,
                status=JobStatus.SUCCEEDED.value,
                bundle_id=bundle.id,
                download_url=signed_url,
                expires_at=expires_at,
            )

    # Need to create/enqueue bundle job
    job = Job(
        lecture_id=lecture.id,
        type=JobType.BUNDLE,
        status=JobStatus.QUEUED,
        payload={
            "rendition": rendition,
            "device_id": str(payload.device_id) if payload.device_id else None,
        },
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Enqueue to background worker queue
    await enqueue_background_job("bundle", str(lecture_id), rendition, str(job.id))

    return OfflineBundleResponse(
        job_id=job.id,
        status=JobStatus.QUEUED.value,
    )


async def get_offline_bundle_status(
    db: AsyncSession,
    job_id: uuid.UUID,
    user: User,
) -> OfflineBundleResponse:
    """Retrieve offline bundle job status and signed download URL if ready."""
    job = await db.get(Job, job_id)
    if job is None or job.type != JobType.BUNDLE:
        raise ApiError(
            status_code=404,
            code="job_not_found",
            message="Offline bundle job not found",
        )

    if job.lecture_id:
        # Enforces can_view_lecture (enrollment check)
        await get_lecture_detail(db, job.lecture_id, user)

    if job.status == JobStatus.SUCCEEDED:
        rendition = job.payload.get("rendition", 480)
        b_stmt = (
            select(Bundle)
            .where(Bundle.lecture_id == job.lecture_id, Bundle.rendition == rendition)
            .order_by(Bundle.version.desc())
        )
        bundle = (await db.execute(b_stmt)).scalars().first()
        if bundle:
            settings = get_settings()
            expires_at = datetime.now(UTC) + timedelta(minutes=settings.media_url_expire_minutes)
            signed_url = generate_signed_media_url(
                path=f"/media/{bundle.path}",
                user_id=user.id,
                expires_at_unix=int(expires_at.timestamp()),
                signing_key=settings.media_signing_key,
            )
            return OfflineBundleResponse(
                job_id=job.id,
                status=job.status.value,
                bundle_id=bundle.id,
                download_url=signed_url,
                expires_at=expires_at,
            )

    return OfflineBundleResponse(
        job_id=job.id,
        status=job.status.value,
    )
