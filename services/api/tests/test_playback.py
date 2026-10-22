"""Playback token, WebVTT captions, chapters, and progress integration tests."""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.enums import EnrollmentRole, LectureStatus, UserRole
from app.models.lecture import Lecture
from app.models.user import User
from app.services.playback_service import verify_signed_media_url
from app.settings import get_settings


@pytest.fixture
async def playback_setup(db_session: AsyncSession) -> dict[str, Any]:
    """Create a professor, enrolled student, non-enrolled student, course, and ready lecture."""
    pwd = "securepassword123"
    prof = User(
        email="prof_playback@univ.edu",
        name="Prof Playback",
        role=UserRole.PROFESSOR,
        password_hash=hash_password(pwd),
    )
    student1 = User(
        email="enrolled@univ.edu",
        name="Enrolled Student",
        role=UserRole.STUDENT,
        password_hash=hash_password(pwd),
    )
    student2 = User(
        email="outsider@univ.edu",
        name="Outside Student",
        role=UserRole.STUDENT,
        password_hash=hash_password(pwd),
    )
    db_session.add_all([prof, student1, student2])
    await db_session.flush()

    course = Course(
        code="CS301",
        title="Distributed Systems",
        owner_id=prof.id,
    )
    db_session.add(course)
    await db_session.flush()

    # Enroll student1
    enrollment = Enrollment(
        user_id=student1.id,
        course_id=course.id,
        role=EnrollmentRole.STUDENT,
    )
    db_session.add(enrollment)

    # Ready lecture
    lecture_ready = Lecture(
        course_id=course.id,
        title="Consensus Algorithms",
        original_path="lectures/test/original.mp4",
        hls_master_path="lectures/test/hls/master.m3u8",
        poster_path="lectures/test/hls/poster.jpg",
        duration_ms=180000,
        status=LectureStatus.READY,
        published=True,
        created_by=prof.id,
    )
    # Processing lecture
    lecture_processing = Lecture(
        course_id=course.id,
        title="Processing Lecture",
        original_path="lectures/test2/original.mp4",
        duration_ms=None,
        status=LectureStatus.PROCESSING,
        published=True,
        created_by=prof.id,
    )
    db_session.add_all([lecture_ready, lecture_processing])
    await db_session.commit()

    return {
        "prof": prof,
        "enrolled_student": student1,
        "outsider_student": student2,
        "course": course,
        "lecture_ready": lecture_ready,
        "lecture_processing": lecture_processing,
        "password": pwd,
    }


async def _get_auth_header(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_playback_token_permissions_and_signature(
    client: AsyncClient,
    playback_setup: dict[str, Any],
) -> None:
    """Verify enrolled student gets signed manifest URL and non-enrolled is refused."""
    pwd = playback_setup["password"]
    lec_id = playback_setup["lecture_ready"].id
    settings = get_settings()

    # 1. Enrolled student gets token
    student_headers = await _get_auth_header(client, playback_setup["enrolled_student"].email, pwd)
    res = await client.post(f"/api/v1/lectures/{lec_id}/playback-token", headers=student_headers)
    assert res.status_code == 200
    data = res.json()
    assert "manifest_url" in data
    assert "expires_at" in data

    manifest_url = data["manifest_url"]
    assert f"/media/lectures/{lec_id}/hls/master.m3u8" in manifest_url
    assert "exp=" in manifest_url
    assert "sig=" in manifest_url
    assert f"uid={playback_setup['enrolled_student'].id}" in manifest_url

    # Parse and verify HMAC signature
    path_part, query = manifest_url.split("?", 1)
    params = dict(param.split("=") for param in query.split("&"))
    is_valid = verify_signed_media_url(
        path=path_part,
        user_id=params["uid"],
        exp=int(params["exp"]),
        sig=params["sig"],
        signing_key=settings.media_signing_key,
    )
    assert is_valid is True

    # 2. Non-enrolled student is refused 403
    outsider_headers = await _get_auth_header(client, playback_setup["outsider_student"].email, pwd)
    res_outsider = await client.post(
        f"/api/v1/lectures/{lec_id}/playback-token", headers=outsider_headers
    )
    assert res_outsider.status_code == 403

    # 3. Processing lecture returns 409 Conflict for course owner
    prof_headers = await _get_auth_header(client, playback_setup["prof"].email, pwd)
    proc_id = playback_setup["lecture_processing"].id
    res_proc = await client.post(f"/api/v1/lectures/{proc_id}/playback-token", headers=prof_headers)
    assert res_proc.status_code == 409


@pytest.mark.asyncio
async def test_captions_and_chapters_endpoints(
    client: AsyncClient,
    playback_setup: dict[str, Any],
) -> None:
    """Verify WebVTT captions and chapter lists are served."""
    pwd = playback_setup["password"]
    lec_id = playback_setup["lecture_ready"].id
    headers = await _get_auth_header(client, playback_setup["enrolled_student"].email, pwd)

    # 1. WebVTT Captions
    res_vtt = await client.get(f"/api/v1/lectures/{lec_id}/captions.vtt", headers=headers)
    assert res_vtt.status_code == 200
    assert "text/vtt" in res_vtt.headers.get("content-type", "")
    assert "WEBVTT" in res_vtt.text
    assert "Consensus Algorithms" in res_vtt.text

    # 2. Chapters
    res_ch = await client.get(f"/api/v1/lectures/{lec_id}/chapters", headers=headers)
    assert res_ch.status_code == 200
    chapters = res_ch.json()
    assert len(chapters) >= 3
    assert chapters[0]["start_ms"] == 0
    assert "title" in chapters[0]


@pytest.mark.asyncio
async def test_playback_progress_save_and_retrieve(
    client: AsyncClient,
    playback_setup: dict[str, Any],
) -> None:
    """Verify saving and retrieving student playback resume position."""
    pwd = playback_setup["password"]
    lec_id = playback_setup["lecture_ready"].id
    headers = await _get_auth_header(client, playback_setup["enrolled_student"].email, pwd)

    # Default progress is 0
    res_init = await client.get(f"/api/v1/lectures/{lec_id}/progress", headers=headers)
    assert res_init.status_code == 200
    assert res_init.json()["position_ms"] == 0
    assert res_init.json()["completed"] is False

    # Save progress to 45,000 ms (45s)
    res_put = await client.put(
        f"/api/v1/lectures/{lec_id}/progress",
        headers=headers,
        json={"position_ms": 45000, "completed": False},
    )
    assert res_put.status_code == 200
    assert res_put.json()["position_ms"] == 45000

    # Retrieve updated progress
    res_get = await client.get(f"/api/v1/lectures/{lec_id}/progress", headers=headers)
    assert res_get.status_code == 200
    assert res_get.json()["position_ms"] == 45000
    assert res_get.json()["completed"] is False


@pytest.mark.asyncio
async def test_internal_video_auth_verification(client: AsyncClient) -> None:
    """Verify Caddy forward_auth target endpoint validates signed parameters."""
    settings = get_settings()
    uid = str(uuid.uuid4())
    path = "/media/lectures/123/hls/master.m3u8"
    exp = 2000000000  # far future

    from app.services.playback_service import generate_signed_media_url

    signed_url = generate_signed_media_url(
        path=path,
        user_id=uuid.UUID(uid),
        expires_at_unix=exp,
        signing_key=settings.media_signing_key,
    )
    query = signed_url.split("?", 1)[1]
    params = dict(p.split("=") for p in query.split("&"))

    # Valid check returns 200
    res_valid = await client.get(
        f"/api/v1/internal/auth/video?path={path}&uid={params['uid']}&exp={params['exp']}&sig={params['sig']}"
    )
    assert res_valid.status_code == 200

    # Tampered signature returns 403
    res_invalid = await client.get(
        f"/api/v1/internal/auth/video?path={path}&uid={params['uid']}&exp={params['exp']}&sig=tampered_sig"
    )
    assert res_invalid.status_code == 403
