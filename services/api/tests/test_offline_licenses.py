"""Tests for devices, Ed25519 license signing, renewal, and revocation."""

import hashlib
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.license import (
    issue_license_token,
    verify_license_token,
)
from app.core.security import hash_password
from app.models.bundle import Bundle
from app.models.course import Course
from app.models.device import OfflineLicense
from app.models.enrollment import Enrollment
from app.models.enums import EnrollmentRole, LectureStatus, UserRole
from app.models.lecture import Lecture, LectureRendition
from app.models.user import User
from app.settings import get_settings


@pytest.fixture
async def license_test_setup(db_session: AsyncSession) -> dict[str, Any]:
    """Create two courses, students, lectures, and renditions."""
    pwd = "securepassword123"
    prof = User(
        email="prof_lic@univ.edu",
        name="Prof License",
        role=UserRole.PROFESSOR,
        password_hash=hash_password(pwd),
    )
    student1 = User(
        email="student1_lic@univ.edu",
        name="Student Enrolled",
        role=UserRole.STUDENT,
        password_hash=hash_password(pwd),
    )
    student2 = User(
        email="student2_lic@univ.edu",
        name="Student Other",
        role=UserRole.STUDENT,
        password_hash=hash_password(pwd),
    )
    db_session.add_all([prof, student1, student2])
    await db_session.flush()

    # Course 1 (Student 1 enrolled)
    course1 = Course(code="CS401", title="Operating Systems", owner_id=prof.id)
    # Course 2 (Student 1 NOT enrolled)
    course2 = Course(code="CS402", title="Compilers", owner_id=prof.id)
    db_session.add_all([course1, course2])
    await db_session.flush()

    enr1 = Enrollment(user_id=student1.id, course_id=course1.id, role=EnrollmentRole.STUDENT)
    db_session.add(enr1)

    lec1 = Lecture(
        course_id=course1.id,
        title="Virtual Memory",
        original_path="lectures/lec1/original.mp4",
        hls_master_path="lectures/lec1/hls/master.m3u8",
        duration_ms=120000,
        status=LectureStatus.READY,
        published=True,
        created_by=prof.id,
    )
    lec2 = Lecture(
        course_id=course2.id,
        title="Lexical Analysis",
        original_path="lectures/lec2/original.mp4",
        hls_master_path="lectures/lec2/hls/master.m3u8",
        duration_ms=180000,
        status=LectureStatus.READY,
        published=True,
        created_by=prof.id,
    )
    db_session.add_all([lec1, lec2])
    await db_session.flush()

    rend1 = LectureRendition(
        lecture_id=lec1.id,
        height=480,
        bitrate_kbps=1200,
        playlist_path=f"lectures/{lec1.id}/hls/480p/index.m3u8",
        size_bytes=10000000,
    )
    rend2 = LectureRendition(
        lecture_id=lec2.id,
        height=480,
        bitrate_kbps=1200,
        playlist_path=f"lectures/{lec2.id}/hls/480p/index.m3u8",
        size_bytes=15000000,
    )
    db_session.add_all([rend1, rend2])
    await db_session.commit()

    return {
        "prof": prof,
        "student1": student1,
        "student2": student2,
        "course1": course1,
        "course2": course2,
        "lec1": lec1,
        "lec2": lec2,
        "password": pwd,
    }


async def _get_auth_header(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_license_verifies_with_public_key(client: AsyncClient) -> None:
    """Verify Ed25519 license token signing, claim contents, and verification via public key."""
    # 1. Fetch public key endpoint
    res_pub = await client.get("/api/v1/license-public-key")
    assert res_pub.status_code == 200
    data_pub = res_pub.json()
    assert "public_key" in data_pub
    assert "BEGIN PUBLIC KEY" in data_pub["public_key"]

    # Also check root endpoint alias
    res_pub_root = await client.get("/license-public-key")
    assert res_pub_root.status_code == 200
    assert res_pub_root.json()["public_key"] == data_pub["public_key"]

    # 2. Issue a sample token
    user_id = uuid.uuid4()
    device_id = uuid.uuid4()
    lecture_id = uuid.uuid4()
    sha256_hash = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    now = datetime.now(UTC)
    exp = now + timedelta(days=14)

    token = issue_license_token(
        user_id=user_id,
        device_id=device_id,
        lecture_id=lecture_id,
        bundle_sha256=sha256_hash,
        issued_at=now,
        expires_at=exp,
    )
    assert isinstance(token, str)

    # 3. Verify with public key
    claims = verify_license_token(token, public_key_pem=data_pub["public_key"])
    assert claims["user_id"] == str(user_id)
    assert claims["device_id"] == str(device_id)
    assert claims["lecture_id"] == str(lecture_id)
    assert claims["bundle_sha256"] == sha256_hash
    assert claims["issued_at"] == now.isoformat()
    assert claims["expires_at"] == exp.isoformat()


@pytest.mark.asyncio
async def test_expired_and_tampered_license_tokens_fail() -> None:
    """Verify that expired or tampered license tokens are rejected."""
    user_id = uuid.uuid4()
    device_id = uuid.uuid4()
    lecture_id = uuid.uuid4()
    sha256_hash = "1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff"

    # 1. Expired token
    past_issued = datetime.now(UTC) - timedelta(days=20)
    past_expires = datetime.now(UTC) - timedelta(days=6)
    expired_token = issue_license_token(
        user_id=user_id,
        device_id=device_id,
        lecture_id=lecture_id,
        bundle_sha256=sha256_hash,
        issued_at=past_issued,
        expires_at=past_expires,
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        verify_license_token(expired_token)

    # 2. Tampered token signature
    valid_token = issue_license_token(
        user_id=user_id,
        device_id=device_id,
        lecture_id=lecture_id,
        bundle_sha256=sha256_hash,
        issued_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=14),
    )
    parts = valid_token.split(".")
    tampered_sig = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
    tampered_token = f"{parts[0]}.{parts[1]}.{tampered_sig}"
    with pytest.raises(jwt.InvalidSignatureError):
        verify_license_token(tampered_token)


@pytest.mark.asyncio
async def test_device_registration_and_fourth_device_refused(
    client: AsyncClient,
    license_test_setup: dict[str, Any],
) -> None:
    """Verify device registration, max 3 active devices limit, listing, and revocation."""
    pwd = license_test_setup["password"]
    student = license_test_setup["student1"]
    headers = await _get_auth_header(client, student.email, pwd)

    # 1. Register 3 devices successfully
    d1 = await client.post(
        "/api/v1/devices",
        json={"name": "Phone", "public_key": "pub_key_1"},
        headers=headers,
    )
    assert d1.status_code == 201
    d1_id = d1.json()["id"]

    d2 = await client.post(
        "/api/v1/devices",
        json={"name": "Tablet", "public_key": "pub_key_2"},
        headers=headers,
    )
    assert d2.status_code == 201

    d3 = await client.post(
        "/api/v1/devices",
        json={"name": "Laptop", "public_key": "pub_key_3"},
        headers=headers,
    )
    assert d3.status_code == 201

    # 2. Fourth device is refused (400)
    d4 = await client.post(
        "/api/v1/devices",
        json={"name": "Desktop", "public_key": "pub_key_4"},
        headers=headers,
    )
    assert d4.status_code == 400
    assert d4.json()["error"]["code"] == "device_limit_reached"

    # 3. List devices shows 3
    list_res = await client.get("/api/v1/devices", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) == 3

    # 4. Revoking one device frees a slot
    del_res = await client.delete(f"/api/v1/devices/{d1_id}", headers=headers)
    assert del_res.status_code == 200

    # 5. Now registering a new device succeeds
    d5 = await client.post(
        "/api/v1/devices",
        json={"name": "Desktop New", "public_key": "pub_key_5"},
        headers=headers,
    )
    assert d5.status_code == 201


@pytest.mark.asyncio
async def test_student_cannot_request_bundle_for_another_course(
    client: AsyncClient,
    license_test_setup: dict[str, Any],
) -> None:
    """Verify an enrolled student cannot request an offline bundle for an un-enrolled course."""
    pwd = license_test_setup["password"]
    student1 = license_test_setup["student1"]
    lec2_id = license_test_setup["lec2"].id  # Course 2 (student 1 is NOT enrolled)
    headers = await _get_auth_header(client, student1.email, pwd)

    # Register device
    dev_res = await client.post(
        "/api/v1/devices",
        json={"name": "Student1 Device", "public_key": "pub_key_std1"},
        headers=headers,
    )
    assert dev_res.status_code == 201
    dev_id = dev_res.json()["id"]

    # Attempting to bundle lecture from course 2 returns 403
    bundle_res = await client.post(
        f"/api/v1/lectures/{lec2_id}/offline-bundle",
        json={"device_id": dev_id, "rendition": 480},
        headers=headers,
    )
    assert bundle_res.status_code == 403


@pytest.mark.asyncio
async def test_bundle_request_creates_license_and_returns_token(
    client: AsyncClient,
    license_test_setup: dict[str, Any],
    db_session: AsyncSession,
) -> None:
    """Verify bundle request generates offline license and signed token."""
    pwd = license_test_setup["password"]
    student1 = license_test_setup["student1"]
    lec1_id = license_test_setup["lec1"].id
    headers = await _get_auth_header(client, student1.email, pwd)

    # Register device
    dev_res = await client.post(
        "/api/v1/devices",
        json={"name": "Study iPad", "public_key": "pub_key_ipad"},
        headers=headers,
    )
    dev_id = dev_res.json()["id"]

    # Pre-populate dummy bundle on disk and database
    settings = get_settings()
    bundle_dir = settings.resolved_storage_root / "bundles" / str(lec1_id)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    zip_path = bundle_dir / "480p-v1.zip"
    dummy_payload = b"test bundle payload for offline licensing"
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("test.bin", dummy_payload)

    bundle_bytes = zip_path.read_bytes()
    bundle_sha = hashlib.sha256(bundle_bytes).hexdigest()

    bundle_row = Bundle(
        id=uuid.uuid4(),
        lecture_id=lec1_id,
        rendition=480,
        version=1,
        path=f"bundles/{lec1_id}/480p-v1.zip",
        size_bytes=len(bundle_bytes),
        sha256=bundle_sha,
        created_at=datetime.now(UTC) + timedelta(minutes=1),
    )
    db_session.add(bundle_row)
    await db_session.commit()

    # Request bundle
    res = await client.post(
        f"/api/v1/lectures/{lec1_id}/offline-bundle",
        json={"device_id": dev_id, "rendition": 480},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "succeeded"
    assert data["size_bytes"] == len(bundle_bytes)
    assert data["sha256"] == bundle_row.sha256
    assert "download_url" in data
    assert "license_token" in data
    assert data["license_token"] is not None

    # Verify license token
    token = data["license_token"]
    claims = verify_license_token(token)
    assert claims["user_id"] == str(student1.id)
    assert claims["device_id"] == str(dev_id)
    assert claims["lecture_id"] == str(lec1_id)
    assert claims["bundle_sha256"] == bundle_row.sha256

    # Verify offline_licenses row in DB
    lic_stmt = select(OfflineLicense).where(
        OfflineLicense.device_id == uuid.UUID(dev_id),
        OfflineLicense.lecture_id == lec1_id,
    )
    lic_db = (await db_session.execute(lic_stmt)).scalar_one()
    assert lic_db.rendition == 480
    assert lic_db.revoked_at is None

    # Verify polling status endpoint also returns license token
    job_id = data["job_id"]
    poll_res = await client.get(f"/api/v1/offline-bundles/{job_id}", headers=headers)
    assert poll_res.status_code == 200
    poll_data = poll_res.json()
    assert poll_data["license_token"] is not None
    assert poll_data["size_bytes"] == len(bundle_bytes)
    assert poll_data["sha256"] == bundle_row.sha256


@pytest.mark.asyncio
async def test_unenrolled_user_renew_returns_revoked(
    client: AsyncClient,
    license_test_setup: dict[str, Any],
    db_session: AsyncSession,
) -> None:
    """Verify that unenrolling a user revokes their license and returns it in revoked list."""
    pwd = license_test_setup["password"]
    prof = license_test_setup["prof"]
    student1 = license_test_setup["student1"]
    course1 = license_test_setup["course1"]
    lec1_id = license_test_setup["lec1"].id

    student_headers = await _get_auth_header(client, student1.email, pwd)
    prof_headers = await _get_auth_header(client, prof.email, pwd)

    # 1. Register device and license
    dev_res = await client.post(
        "/api/v1/devices",
        json={"name": "Student Laptop", "public_key": "pub_key_laptop"},
        headers=student_headers,
    )
    dev_id = dev_res.json()["id"]

    lic = OfflineLicense(
        id=uuid.uuid4(),
        user_id=student1.id,
        device_id=uuid.UUID(dev_id),
        lecture_id=lec1_id,
        rendition=480,
        issued_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=14),
    )
    db_session.add(lic)
    await db_session.commit()

    # 2. Before unenrollment, renew extends the license
    res_renew1 = await client.post(
        "/api/v1/offline-licenses/renew",
        json={"device_id": dev_id},
        headers=student_headers,
    )
    assert res_renew1.status_code == 200
    assert len(res_renew1.json()["renewed"]) == 1
    assert len(res_renew1.json()["revoked"]) == 0

    # 3. Professor removes student from course
    del_enr = await client.delete(
        f"/api/v1/courses/{course1.id}/enrollments/{student1.id}",
        headers=prof_headers,
    )
    assert del_enr.status_code == 200

    # 4. Now student attempts renew -> lecture is listed under revoked
    res_renew2 = await client.post(
        "/api/v1/offline-licenses/renew",
        json={"device_id": dev_id},
        headers=student_headers,
    )
    assert res_renew2.status_code == 200
    data2 = res_renew2.json()
    assert len(data2["renewed"]) == 0
    assert str(lec1_id) in [str(x) for x in data2["revoked"]]

    # Verify license is revoked in DB
    await db_session.refresh(lic)
    assert lic.revoked_at is not None


@pytest.mark.asyncio
async def test_unpublishing_lecture_revokes_license(
    client: AsyncClient,
    license_test_setup: dict[str, Any],
    db_session: AsyncSession,
) -> None:
    """Verify unpublishing a lecture revokes offline licenses."""
    pwd = license_test_setup["password"]
    prof = license_test_setup["prof"]
    student1 = license_test_setup["student1"]
    lec1_id = license_test_setup["lec1"].id

    student_headers = await _get_auth_header(client, student1.email, pwd)
    prof_headers = await _get_auth_header(client, prof.email, pwd)

    # Register device and license
    dev_res = await client.post(
        "/api/v1/devices",
        json={"name": "Tablet", "public_key": "pub_key_tab"},
        headers=student_headers,
    )
    dev_id = dev_res.json()["id"]

    lic = OfflineLicense(
        id=uuid.uuid4(),
        user_id=student1.id,
        device_id=uuid.UUID(dev_id),
        lecture_id=lec1_id,
        rendition=480,
        issued_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=14),
    )
    db_session.add(lic)
    await db_session.commit()

    # Professor unpublishes lecture
    patch_res = await client.patch(
        f"/api/v1/lectures/{lec1_id}",
        json={"published": False},
        headers=prof_headers,
    )
    assert patch_res.status_code == 200

    # Student renews -> lecture listed under revoked
    renew_res = await client.post(
        "/api/v1/offline-licenses/renew",
        json={"device_id": dev_id},
        headers=student_headers,
    )
    assert renew_res.status_code == 200
    assert str(lec1_id) in [str(x) for x in renew_res.json()["revoked"]]
