"""Lectures, chunked upload, and authorization integration tests."""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.course import Course
from app.models.enums import JobStatus, JobType, LectureStatus, UserRole
from app.models.job import Job
from app.models.lecture import Lecture
from app.models.user import User
from app.settings import get_settings


@pytest.fixture
async def lecture_setup(db_session: AsyncSession) -> dict[str, Any]:
    """Seed users, a course, and return authorization credentials."""
    prof1 = User(
        id=uuid.uuid4(),
        email="prof_lec@campus.local",
        name="Prof. Lecture",
        role=UserRole.PROFESSOR,
        password_hash=hash_password("Pass123!"),
        is_active=True,
    )
    prof2 = User(
        id=uuid.uuid4(),
        email="prof_other@campus.local",
        name="Prof. Other",
        role=UserRole.PROFESSOR,
        password_hash=hash_password("Pass123!"),
        is_active=True,
    )
    student1 = User(
        id=uuid.uuid4(),
        email="student_enrolled@campus.local",
        name="Enrolled Student",
        role=UserRole.STUDENT,
        password_hash=hash_password("Pass123!"),
        is_active=True,
    )
    student2 = User(
        id=uuid.uuid4(),
        email="student_not_enrolled@campus.local",
        name="External Student",
        role=UserRole.STUDENT,
        password_hash=hash_password("Pass123!"),
        is_active=True,
    )

    db_session.add_all([prof1, prof2, student1, student2])
    await db_session.commit()

    # Create Course owned by prof1
    course = Course(
        id=uuid.uuid4(),
        code="CS501",
        title="Distributed Systems",
        owner_id=prof1.id,
    )
    db_session.add(course)
    await db_session.commit()

    return {
        "prof1": prof1,
        "prof2": prof2,
        "student1": student1,
        "student2": student2,
        "course": course,
        "password": "Pass123!",
    }


async def _get_auth_header(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_lecture_and_validation(
    client: AsyncClient,
    lecture_setup: dict[str, Any],
) -> None:
    """Create lecture validation: allowed types, owner authorization."""
    pwd = lecture_setup["password"]
    prof1_h = await _get_auth_header(client, lecture_setup["prof1"].email, pwd)
    prof2_h = await _get_auth_header(client, lecture_setup["prof2"].email, pwd)
    student_h = await _get_auth_header(client, lecture_setup["student1"].email, pwd)
    course_id = lecture_setup["course"].id

    # 1. Valid video extensions: mp4, mov, mkv, webm
    resp_mp4 = await client.post(
        f"/api/v1/courses/{course_id}/lectures",
        json={"title": "Lecture 1", "filename": "video.mp4"},
        headers=prof1_h,
    )
    assert resp_mp4.status_code == 201
    data = resp_mp4.json()
    assert data["lecture"]["title"] == "Lecture 1"
    assert data["lecture"]["status"] == "uploaded"
    assert "upload_url" in data
    assert data["upload_url"].endswith(f"/api/v1/lectures/{data['lecture']['id']}/upload")

    # 2. Invalid extension (.txt, .avi, .exe)
    resp_invalid = await client.post(
        f"/api/v1/courses/{course_id}/lectures",
        json={"title": "Invalid File", "filename": "document.txt"},
        headers=prof1_h,
    )
    assert resp_invalid.status_code == 400
    assert resp_invalid.json()["error"]["code"] == "invalid_file_type"

    # 3. Non-owner professor cannot create lecture in this course -> 403
    resp_other_prof = await client.post(
        f"/api/v1/courses/{course_id}/lectures",
        json={"title": "Intruder Lecture", "filename": "file.mkv"},
        headers=prof2_h,
    )
    assert resp_other_prof.status_code == 403

    # 4. Student cannot create lecture -> 403
    resp_student = await client.post(
        f"/api/v1/courses/{course_id}/lectures",
        json={"title": "Student Lecture", "filename": "file.webm"},
        headers=student_h,
    )
    assert resp_student.status_code == 403


@pytest.mark.asyncio
async def test_resumable_chunked_upload_and_interruption(
    client: AsyncClient,
    db_session: AsyncSession,
    lecture_setup: dict[str, Any],
) -> None:
    """Interrupted and resumed chunked upload accurately reconstructs original file."""
    pwd = lecture_setup["password"]
    prof1_h = await _get_auth_header(client, lecture_setup["prof1"].email, pwd)
    course_id = lecture_setup["course"].id

    # 1. Create lecture
    c_resp = await client.post(
        f"/api/v1/courses/{course_id}/lectures",
        json={"title": "Resumable Upload Lecture", "filename": "lecture.mp4"},
        headers=prof1_h,
    )
    assert c_resp.status_code == 201
    lecture_id = c_resp.json()["lecture"]["id"]
    upload_url = c_resp.json()["upload_url"]

    # 2. Simulated binary data of 3000 bytes
    total_size = 3000
    full_data = bytes([i % 256 for i in range(total_size)])

    chunk1 = full_data[0:1000]  # bytes 0-999
    chunk2 = full_data[1000:2000]  # bytes 1000-1999
    chunk3 = full_data[2000:3000]  # bytes 2000-2999

    # 3. Upload Chunk 1: bytes 0-999/3000
    resp_c1 = await client.put(
        upload_url,
        content=chunk1,
        headers={**prof1_h, "Content-Range": f"bytes 0-999/{total_size}"},
    )
    assert resp_c1.status_code == 200
    assert resp_c1.json()["current_size"] == 1000
    assert resp_c1.json()["status"] == "incomplete"

    # Simulate interruption: verify partial file on disk
    settings = get_settings()
    disk_path = settings.storage_root / f"lectures/{lecture_id}/original.mp4"
    assert disk_path.exists()
    assert disk_path.stat().st_size == 1000
    assert disk_path.read_bytes() == chunk1

    # 4. Resume upload with Chunk 2: bytes 1000-1999/3000
    resp_c2 = await client.put(
        upload_url,
        content=chunk2,
        headers={**prof1_h, "Content-Range": f"bytes 1000-1999/{total_size}"},
    )
    assert resp_c2.status_code == 200
    assert resp_c2.json()["current_size"] == 2000
    assert resp_c2.json()["status"] == "incomplete"
    assert disk_path.stat().st_size == 2000

    # 5. Final Chunk 3: bytes 2000-2999/3000
    resp_c3 = await client.put(
        upload_url,
        content=chunk3,
        headers={**prof1_h, "Content-Range": f"bytes 2000-2999/{total_size}"},
    )
    assert resp_c3.status_code == 200
    assert resp_c3.json()["current_size"] == 3000
    assert resp_c3.json()["status"] == "uploaded"

    # 6. Complete upload
    complete_resp = await client.post(
        f"/api/v1/lectures/{lecture_id}/upload/complete",
        headers=prof1_h,
    )
    assert complete_resp.status_code == 200
    data = complete_resp.json()
    assert data["status"] == "processing"
    assert data["lecture"]["status"] == "processing"

    # 7. Verify file on disk matches full original data
    assert disk_path.read_bytes() == full_data

    # 8. Verify Job row in database
    job_stmt = select(Job).where(Job.lecture_id == uuid.UUID(lecture_id))
    job = (await db_session.execute(job_stmt)).scalar_one()
    assert job.type == JobType.TRANSCODE
    assert job.status == JobStatus.QUEUED

    # Clean up test storage file
    if disk_path.exists():
        disk_path.unlink()
        if disk_path.parent.exists():
            disk_path.parent.rmdir()


@pytest.mark.asyncio
async def test_upload_chunk_size_mismatch_and_file_too_large(
    client: AsyncClient,
    lecture_setup: dict[str, Any],
) -> None:
    """Validate chunk size against Content-Range header and max upload limits."""
    pwd = lecture_setup["password"]
    prof1_h = await _get_auth_header(client, lecture_setup["prof1"].email, pwd)
    course_id = lecture_setup["course"].id

    c_resp = await client.post(
        f"/api/v1/courses/{course_id}/lectures",
        json={"title": "Validation Lecture", "filename": "video.mp4"},
        headers=prof1_h,
    )
    lecture_id = c_resp.json()["lecture"]["id"]
    upload_url = f"/api/v1/lectures/{lecture_id}/upload"

    # Chunk size mismatch: range claims 100 bytes (0-99), but payload is 10 bytes
    bad_chunk_resp = await client.put(
        upload_url,
        content=b"0123456789",
        headers={**prof1_h, "Content-Range": "bytes 0-99/1000"},
    )
    assert bad_chunk_resp.status_code == 400
    assert bad_chunk_resp.json()["error"]["code"] == "chunk_size_mismatch"

    # File size exceeding max: specify total > 8GB
    oversize_total = 10 * 1024 * 1024 * 1024  # 10 GB
    oversize_resp = await client.put(
        upload_url,
        content=b"0123456789",
        headers={**prof1_h, "Content-Range": f"bytes 0-9/{oversize_total}"},
    )
    assert oversize_resp.status_code == 413
    assert oversize_resp.json()["error"]["code"] == "file_too_large"


@pytest.mark.asyncio
async def test_student_cannot_see_unpublished_or_non_ready_lectures(
    client: AsyncClient,
    db_session: AsyncSession,
    lecture_setup: dict[str, Any],
) -> None:
    """Students must NEVER see unpublished or non-ready lectures."""
    pwd = lecture_setup["password"]
    prof1_h = await _get_auth_header(client, lecture_setup["prof1"].email, pwd)
    student1_h = await _get_auth_header(client, lecture_setup["student1"].email, pwd)
    student2_h = await _get_auth_header(client, lecture_setup["student2"].email, pwd)
    course_id = lecture_setup["course"].id

    # Enroll student 1 into the course
    await client.post(
        f"/api/v1/courses/{course_id}/enrollments",
        json={"emails": [lecture_setup["student1"].email]},
        headers=prof1_h,
    )

    # Professor creates lecture
    c_resp = await client.post(
        f"/api/v1/courses/{course_id}/lectures",
        json={"title": "Secret Lecture", "filename": "secret.mp4"},
        headers=prof1_h,
    )
    lecture_id = c_resp.json()["lecture"]["id"]

    # Stage 1: uploaded, published=False
    # Student 1 lists lectures -> empty
    list1 = await client.get(f"/api/v1/courses/{course_id}/lectures", headers=student1_h)
    assert list1.status_code == 200
    assert len(list1.json()) == 0

    # Student 1 gets detail -> 403 Forbidden
    detail1 = await client.get(f"/api/v1/lectures/{lecture_id}", headers=student1_h)
    assert detail1.status_code == 403

    # Stage 2: professor publishes lecture, but status is still 'uploaded' / not 'ready'
    await client.patch(
        f"/api/v1/lectures/{lecture_id}",
        json={"published": True},
        headers=prof1_h,
    )
    list2 = await client.get(f"/api/v1/courses/{course_id}/lectures", headers=student1_h)
    assert list2.status_code == 200
    assert len(list2.json()) == 0
    detail2 = await client.get(f"/api/v1/lectures/{lecture_id}", headers=student1_h)
    assert detail2.status_code == 403

    # Stage 3: set status='ready'
    settings = get_settings()
    dummy_file = settings.storage_root / f"lectures/{lecture_id}/original.mp4"
    dummy_file.parent.mkdir(parents=True, exist_ok=True)
    dummy_file.write_bytes(b"dummy video data")

    # Call complete upload to change status to processing
    await client.post(f"/api/v1/lectures/{lecture_id}/upload/complete", headers=prof1_h)

    # Mark as ready directly via db_session
    lec = await db_session.get(Lecture, uuid.UUID(lecture_id))
    assert lec is not None
    lec.status = LectureStatus.READY
    lec.published = True
    await db_session.commit()

    # Now enrolled Student 1 can see and view the lecture
    list3 = await client.get(f"/api/v1/courses/{course_id}/lectures", headers=student1_h)
    assert list3.status_code == 200
    assert len(list3.json()) == 1
    assert list3.json()[0]["id"] == lecture_id

    detail3 = await client.get(f"/api/v1/lectures/{lecture_id}", headers=student1_h)
    assert detail3.status_code == 200
    assert detail3.json()["title"] == "Secret Lecture"

    # Non-enrolled Student 2 CANNOT see or view -> 403
    list_student2 = await client.get(f"/api/v1/courses/{course_id}/lectures", headers=student2_h)
    assert list_student2.status_code == 403
    detail_student2 = await client.get(f"/api/v1/lectures/{lecture_id}", headers=student2_h)
    assert detail_student2.status_code == 403

    # Clean up dummy file
    if dummy_file.exists():
        dummy_file.unlink()
        if dummy_file.parent.exists():
            dummy_file.parent.rmdir()


@pytest.mark.asyncio
async def test_patch_and_delete_lecture(
    client: AsyncClient,
    lecture_setup: dict[str, Any],
) -> None:
    """Only owning professor can patch and delete a lecture."""
    pwd = lecture_setup["password"]
    prof1_h = await _get_auth_header(client, lecture_setup["prof1"].email, pwd)
    prof2_h = await _get_auth_header(client, lecture_setup["prof2"].email, pwd)
    student1_h = await _get_auth_header(client, lecture_setup["student1"].email, pwd)
    course_id = lecture_setup["course"].id

    # Create lecture
    c_resp = await client.post(
        f"/api/v1/courses/{course_id}/lectures",
        json={"title": "Delete Me", "filename": "del.mp4"},
        headers=prof1_h,
    )
    lecture_id = c_resp.json()["lecture"]["id"]

    # Student cannot patch -> 403
    p_student = await client.patch(
        f"/api/v1/lectures/{lecture_id}",
        json={"title": "Hacked"},
        headers=student1_h,
    )
    assert p_student.status_code == 403

    # Non-owner professor cannot patch -> 403
    p_prof2 = await client.patch(
        f"/api/v1/lectures/{lecture_id}",
        json={"title": "Hacked 2"},
        headers=prof2_h,
    )
    assert p_prof2.status_code == 403

    # Owner patches title -> 200
    p_owner = await client.patch(
        f"/api/v1/lectures/{lecture_id}",
        json={"title": "Updated Title", "position": 5},
        headers=prof1_h,
    )
    assert p_owner.status_code == 200
    assert p_owner.json()["title"] == "Updated Title"
    assert p_owner.json()["position"] == 5

    # Non-owner cannot delete -> 403
    del_prof2 = await client.delete(f"/api/v1/lectures/{lecture_id}", headers=prof2_h)
    assert del_prof2.status_code == 403

    # Owner deletes lecture -> 200
    del_owner = await client.delete(f"/api/v1/lectures/{lecture_id}", headers=prof1_h)
    assert del_owner.status_code == 200
    assert del_owner.json() == {"status": "ok"}

    # Lecture is gone -> 404
    get_gone = await client.get(f"/api/v1/lectures/{lecture_id}", headers=prof1_h)
    assert get_gone.status_code == 404
