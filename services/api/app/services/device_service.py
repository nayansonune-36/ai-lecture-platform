"""Device management and offline license renewal service."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, forbidden
from app.core.license import issue_license_token
from app.models.bundle import Bundle
from app.models.course import Course
from app.models.device import Device, OfflineLicense
from app.models.enrollment import Enrollment
from app.models.enums import LectureStatus, UserRole
from app.models.lecture import Lecture
from app.models.user import User
from app.schemas.device import (
    DeviceCreate,
    DeviceOut,
    LicenseRenewRequest,
    LicenseRenewResponse,
    RenewedLicenseOut,
)


async def register_device(
    db: AsyncSession,
    payload: DeviceCreate,
    user: User,
) -> DeviceOut:
    """Register a new device for offline playback, enforcing max 3 active devices per user."""
    # Count active devices
    count_stmt = select(func.count(Device.id)).where(
        Device.user_id == user.id,
        Device.revoked_at.is_(None),
    )
    active_count = (await db.execute(count_stmt)).scalar_one()

    if active_count >= 3:
        raise ApiError(
            status_code=400,
            code="device_limit_reached",
            message="Maximum of 3 active devices reached. Revoke an existing device first.",
        )

    device = Device(
        id=uuid.uuid4(),
        user_id=user.id,
        name=payload.name,
        public_key=payload.public_key,
        created_at=datetime.now(UTC),
        revoked_at=None,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)

    return DeviceOut.model_validate(device)


async def list_user_devices(
    db: AsyncSession,
    user: User,
) -> list[DeviceOut]:
    """List all registered devices for the current user."""
    stmt = select(Device).where(Device.user_id == user.id).order_by(Device.created_at.desc())
    devices = (await db.execute(stmt)).scalars().all()
    return [DeviceOut.model_validate(d) for d in devices]


async def revoke_device(
    db: AsyncSession,
    device_id: uuid.UUID,
    user: User,
) -> None:
    """Revoke a device and all its offline licenses."""
    device = await db.get(Device, device_id)
    if device is None:
        raise ApiError(status_code=404, code="device_not_found", message="Device not found")

    if user.role != UserRole.ADMIN and device.user_id != user.id:
        raise forbidden("You cannot delete another user's device", code="forbidden")

    now = datetime.now(UTC)
    device.revoked_at = now

    # Revoke all offline licenses associated with this device
    await db.execute(
        update(OfflineLicense)
        .where(
            OfflineLicense.device_id == device.id,
            OfflineLicense.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )

    await db.commit()


async def check_user_can_view_lecture(
    db: AsyncSession,
    lecture_id: uuid.UUID,
    user: User,
) -> bool:
    """Determine if a user can currently view a lecture."""
    lecture = await db.get(Lecture, lecture_id)
    if lecture is None:
        return False

    course = await db.get(Course, lecture.course_id)
    if course is None:
        return False

    if user.role == UserRole.ADMIN or course.owner_id == user.id:
        return True

    # Check enrollment
    enr_stmt = select(Enrollment).where(
        Enrollment.course_id == course.id,
        Enrollment.user_id == user.id,
    )
    enrollment = (await db.execute(enr_stmt)).scalar_one_or_none()
    if enrollment is None:
        return False

    # Students require published and ready lecture
    return bool(lecture.published and lecture.status == LectureStatus.READY)


async def renew_offline_licenses(
    db: AsyncSession,
    payload: LicenseRenewRequest,
    user: User,
) -> LicenseRenewResponse:
    """Extend valid licenses and revoke expired/unauthorized ones."""
    device = await db.get(Device, payload.device_id)
    if device is None:
        raise ApiError(status_code=404, code="device_not_found", message="Device not found")

    if device.user_id != user.id or device.revoked_at is not None:
        raise forbidden(
            "Device is not valid, not owned by user, or has been revoked",
            code="forbidden",
        )

    stmt = select(OfflineLicense).where(OfflineLicense.device_id == device.id)
    licenses = (await db.execute(stmt)).scalars().all()

    renewed: list[RenewedLicenseOut] = []
    revoked: list[uuid.UUID] = []

    now = datetime.now(UTC)
    new_expires_at = now + timedelta(days=14)

    for lic in licenses:
        can_view = await check_user_can_view_lecture(db, lic.lecture_id, user)

        if can_view and lic.revoked_at is None:
            # User is still enrolled and permitted to view
            lic.issued_at = now
            lic.expires_at = new_expires_at
            lic.revoked_at = None

            # Look up bundle sha256
            b_stmt = (
                select(Bundle)
                .where(Bundle.lecture_id == lic.lecture_id, Bundle.rendition == lic.rendition)
                .order_by(Bundle.version.desc())
            )
            bundle = (await db.execute(b_stmt)).scalars().first()
            bundle_sha = bundle.sha256 if bundle else ""

            token = issue_license_token(
                user_id=user.id,
                device_id=device.id,
                lecture_id=lic.lecture_id,
                bundle_sha256=bundle_sha,
                issued_at=now,
                expires_at=new_expires_at,
            )

            renewed.append(
                RenewedLicenseOut(
                    lecture_id=lic.lecture_id,
                    token=token,
                    expires_at=new_expires_at,
                )
            )
        else:
            # Cannot view or already revoked
            lic.revoked_at = now
            revoked.append(lic.lecture_id)

    await db.commit()

    return LicenseRenewResponse(
        device_id=device.id,
        renewed=renewed,
        revoked=revoked,
    )
