"""Tests for offline bundle estimation, authorization, and Range request resumption."""

import hashlib
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.bundle import Bundle
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.enums import EnrollmentRole, JobStatus, JobType, LectureStatus, UserRole
from app.models.job import Job
from app.models.lecture import Lecture, LectureRendition
from app.models.user import User
from app.settings import get_settings


@pytest.fixture
async def bundle_setup(db_session: AsyncSession) -> dict[str, Any]:
    """Create course, enrolled student, non-enrolled student, ready lecture, and rendition."""
    pwd = "securepassword123"
    prof = User(
        email="prof_bundle@univ.edu",
        name="Prof Bundle",
        role=UserRole.PROFESSOR,
        password_hash=hash_password(pwd),
    )
    enrolled_student = User(
        email="student_enrolled@univ.edu",
        name="Enrolled Student",
        role=UserRole.STUDENT,
        password_hash=hash_password(pwd),
    )
    outsider_student = User(
        email="student_outsider@univ.edu",
        name="Outsider Student",
        role=UserRole.STUDENT,
        password_hash=hash_password(pwd),
    )
    db_session.add_all([prof, enrolled_student, outsider_student])
    await db_session.flush()

    course = Course(
        code="EE401",
        title="Digital Signal Processing",
        owner_id=prof.id,
    )
    db_session.add(course)
    await db_session.flush()

    enrollment = Enrollment(
        user_id=enrolled_student.id,
        course_id=course.id,
        role=EnrollmentRole.STUDENT,
    )
    db_session.add(enrollment)

    lecture = Lecture(
        course_id=course.id,
        title="Fourier Transform Fundamentals",
        original_path="lectures/test/original.mp4",
        hls_master_path="lectures/test/hls/master.m3u8",
        poster_path="lectures/test/hls/poster.jpg",
        duration_ms=240000,
        status=LectureStatus.READY,
        published=True,
        created_by=prof.id,
    )
    db_session.add(lecture)
    await db_session.flush()

    rendition_480 = LectureRendition(
        lecture_id=lecture.id,
        height=480,
        bitrate_kbps=1200,
        playlist_path=f"lectures/{lecture.id}/hls/480p/index.m3u8",
        size_bytes=36000000,
    )
    db_session.add(rendition_480)
    await db_session.commit()

    return {
        "prof": prof,
        "enrolled_student": enrolled_student,
        "outsider_student": outsider_student,
        "course": course,
        "lecture": lecture,
        "rendition_480": rendition_480,
        "password": pwd,
    }


async def _get_auth_header(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_offline_estimate_endpoint(
    client: AsyncClient,
    bundle_setup: dict[str, Any],
) -> None:
    """Verify estimate endpoint returns approximate size for enrolled user and rejects outsider."""
    pwd = bundle_setup["password"]
    lec_id = bundle_setup["lecture"].id

    enrolled_headers = await _get_auth_header(client, bundle_setup["enrolled_student"].email, pwd)
    outsider_headers = await _get_auth_header(client, bundle_setup["outsider_student"].email, pwd)

    # 1. Enrolled user gets estimate
    res_enrolled = await client.get(
        f"/api/v1/lectures/{lec_id}/offline-estimate?rendition=480",
        headers=enrolled_headers,
    )
    assert res_enrolled.status_code == 200
    data = res_enrolled.json()
    assert data["lecture_id"] == str(lec_id)
    assert data["rendition"] == 480
    assert data["estimated_size_bytes"] > 0

    # 2. Non-enrolled user is refused 403
    res_outsider = await client.get(
        f"/api/v1/lectures/{lec_id}/offline-estimate?rendition=480",
        headers=outsider_headers,
    )
    assert res_outsider.status_code == 403

    # 3. Invalid rendition returns 400
    res_invalid = await client.get(
        f"/api/v1/lectures/{lec_id}/offline-estimate?rendition=1080",
        headers=enrolled_headers,
    )
    assert res_invalid.status_code == 400


@pytest.mark.asyncio
async def test_non_enrolled_user_cannot_get_download_url(
    client: AsyncClient,
    bundle_setup: dict[str, Any],
    db_session: AsyncSession,
) -> None:
    """Verify a student not enrolled in the course cannot request a bundle or access bundle job."""
    pwd = bundle_setup["password"]
    lec_id = bundle_setup["lecture"].id
    outsider_headers = await _get_auth_header(client, bundle_setup["outsider_student"].email, pwd)

    # Non-enrolled user attempting to queue a bundle gets 403
    res_queue = await client.post(
        f"/api/v1/lectures/{lec_id}/offline-bundle",
        json={"rendition": 480},
        headers=outsider_headers,
    )
    assert res_queue.status_code == 403

    # Create a job record directly in DB
    job = Job(
        lecture_id=lec_id,
        type=JobType.BUNDLE,
        status=JobStatus.SUCCEEDED,
        payload={"rendition": 480},
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    # Non-enrolled user attempting to poll job gets 403
    res_poll = await client.get(
        f"/api/v1/offline-bundles/{job.id}",
        headers=outsider_headers,
    )
    assert res_poll.status_code == 403


@pytest.mark.asyncio
async def test_bundle_download_and_range_resumption(
    client: AsyncClient,
    bundle_setup: dict[str, Any],
    db_session: AsyncSession,
) -> None:
    """Verify enrolled user gets signed download URL and Range requests resume downloads."""
    pwd = bundle_setup["password"]
    lec_id = bundle_setup["lecture"].id
    settings = get_settings()
    storage_root = settings.resolved_storage_root

    # Create dummy bundle zip on disk
    bundle_dir = storage_root / "bundles" / str(lec_id)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    zip_path = bundle_dir / "480p-v1.zip"

    dummy_payload = b"A" * 1024 + b"B" * 1024  # 2048 bytes of test data
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("test.bin", dummy_payload)

    total_zip_bytes = zip_path.read_bytes()
    total_size = len(total_zip_bytes)
    zip_sha256 = hashlib.sha256(total_zip_bytes).hexdigest()

    # Record bundle in database
    bundle_row = Bundle(
        id=uuid.uuid4(),
        lecture_id=lec_id,
        rendition=480,
        version=1,
        path=f"bundles/{lec_id}/480p-v1.zip",
        size_bytes=total_size,
        sha256=zip_sha256,
        created_at=datetime.now(UTC) + timedelta(minutes=1),
    )
    db_session.add(bundle_row)
    await db_session.commit()

    # Enrolled student requests bundle
    enrolled_headers = await _get_auth_header(client, bundle_setup["enrolled_student"].email, pwd)
    res = await client.post(
        f"/api/v1/lectures/{lec_id}/offline-bundle",
        json={"rendition": 480},
        headers=enrolled_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "succeeded"
    assert "download_url" in data
    download_url = data["download_url"]
    assert f"/media/bundles/{lec_id}/480p-v1.zip" in download_url
    assert "sig=" in download_url

    # 1. Tampered signature is rejected with 403
    tampered_url = download_url.replace("sig=", "sig=tampered_invalid_")
    res_tampered = await client.get(tampered_url)
    assert res_tampered.status_code == 403

    # 2. Valid URL without Range header returns 200 OK and full file
    res_full = await client.get(download_url)
    assert res_full.status_code == 200
    assert res_full.headers.get("accept-ranges") == "bytes"
    assert res_full.content == total_zip_bytes

    # 3. Range request for first 100 bytes (0-99)
    res_part1 = await client.get(download_url, headers={"Range": "bytes=0-99"})
    assert res_part1.status_code == 206
    assert res_part1.headers.get("content-range") == f"bytes 0-99/{total_size}"
    assert len(res_part1.content) == 100
    assert res_part1.content == total_zip_bytes[:100]

    # 4. Range request for remaining bytes (100-) to resume download
    res_part2 = await client.get(download_url, headers={"Range": "bytes=100-"})
    assert res_part2.status_code == 206
    assert res_part2.headers.get("content-range") == f"bytes 100-{total_size - 1}/{total_size}"
    assert len(res_part2.content) == total_size - 100
    assert res_part2.content == total_zip_bytes[100:]

    # Resumed download byte-for-byte matches full file
    reassembled = res_part1.content + res_part2.content
    assert reassembled == total_zip_bytes
