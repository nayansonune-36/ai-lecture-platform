"""Courses and enrollments authorization and management integration tests."""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import User


@pytest.fixture
async def course_setup(db_session: AsyncSession) -> dict[str, Any]:
    """Seed professors and students for course authorization testing."""
    prof1 = User(
        id=uuid.uuid4(),
        email="prof1@campus.local",
        name="Prof. Raman",
        role=UserRole.PROFESSOR,
        password_hash=hash_password("Pass123!"),
        is_active=True,
    )
    prof2 = User(
        id=uuid.uuid4(),
        email="prof2@campus.local",
        name="Prof. Bose",
        role=UserRole.PROFESSOR,
        password_hash=hash_password("Pass123!"),
        is_active=True,
    )
    student1 = User(
        id=uuid.uuid4(),
        email="student1@campus.local",
        name="Student One",
        role=UserRole.STUDENT,
        password_hash=hash_password("Pass123!"),
        is_active=True,
    )
    student2 = User(
        id=uuid.uuid4(),
        email="student2@campus.local",
        name="Student Two",
        role=UserRole.STUDENT,
        password_hash=hash_password("Pass123!"),
        is_active=True,
    )

    db_session.add_all([prof1, prof2, student1, student2])
    await db_session.commit()

    return {
        "prof1": prof1,
        "prof2": prof2,
        "student1": student1,
        "student2": student2,
        "password": "Pass123!",
    }


async def _get_auth_header(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    """Helper to log in and get Authorization header."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_professor_can_create_course(
    client: AsyncClient,
    course_setup: dict[str, Any],
) -> None:
    """Professors can create courses, students cannot."""
    prof_header = await _get_auth_header(
        client,
        course_setup["prof1"].email,
        course_setup["password"],
    )

    # Professor creates course
    create_resp = await client.post(
        "/api/v1/courses",
        json={
            "code": "PHY201",
            "title": "Quantum Mechanics",
            "description": "Intro to quantum theory",
            "term": "2026-autumn",
        },
        headers=prof_header,
    )
    assert create_resp.status_code == 201
    course_data = create_resp.json()
    assert course_data["code"] == "PHY201"
    assert course_data["owner_id"] == str(course_setup["prof1"].id)

    # Student attempts to create course -> 403
    student_header = await _get_auth_header(
        client,
        course_setup["student1"].email,
        course_setup["password"],
    )
    student_resp = await client.post(
        "/api/v1/courses",
        json={"code": "CS101", "title": "Intro to CS", "term": "2026-autumn"},
        headers=student_header,
    )
    assert student_resp.status_code == 403
    assert student_resp.json()["error"]["code"] == "insufficient_permissions"


@pytest.mark.asyncio
async def test_student_sees_only_enrolled_courses(
    client: AsyncClient,
    course_setup: dict[str, Any],
) -> None:
    """Students only see courses they are enrolled in on GET /courses."""
    prof1_header = await _get_auth_header(
        client,
        course_setup["prof1"].email,
        course_setup["password"],
    )
    student1_header = await _get_auth_header(
        client,
        course_setup["student1"].email,
        course_setup["password"],
    )

    # Professor creates Course A and Course B
    c_a = await client.post(
        "/api/v1/courses",
        json={"code": "MATH101", "title": "Calculus I", "term": "2026-autumn"},
        headers=prof1_header,
    )
    c_b = await client.post(
        "/api/v1/courses",
        json={"code": "MATH102", "title": "Calculus II", "term": "2026-autumn"},
        headers=prof1_header,
    )
    course_a_id = c_a.json()["id"]
    course_b_id = c_b.json()["id"]

    # Student initially sees 0 courses
    list_resp1 = await client.get("/api/v1/courses", headers=student1_header)
    assert list_resp1.status_code == 200
    assert len(list_resp1.json()) == 0

    # Enroll student in Course A only
    enroll_resp = await client.post(
        f"/api/v1/courses/{course_a_id}/enrollments",
        json={"emails": [course_setup["student1"].email]},
        headers=prof1_header,
    )
    assert enroll_resp.status_code == 200

    # Student now sees only Course A
    list_resp2 = await client.get("/api/v1/courses", headers=student1_header)
    assert list_resp2.status_code == 200
    courses_seen = list_resp2.json()
    assert len(courses_seen) == 1
    assert courses_seen[0]["id"] == course_a_id

    # Student can view Course A detail
    detail_a = await client.get(f"/api/v1/courses/{course_a_id}", headers=student1_header)
    assert detail_a.status_code == 200
    assert detail_a.json()["code"] == "MATH101"

    # Student CANNOT view Course B detail -> 403 Forbidden
    detail_b = await client.get(f"/api/v1/courses/{course_b_id}", headers=student1_header)
    assert detail_b.status_code == 403
    assert detail_b.json()["error"]["code"] == "forbidden"


@pytest.mark.asyncio
async def test_only_owner_can_edit_course(
    client: AsyncClient,
    course_setup: dict[str, Any],
) -> None:
    """Only the owning professor can patch course metadata."""
    prof1_header = await _get_auth_header(
        client,
        course_setup["prof1"].email,
        course_setup["password"],
    )
    prof2_header = await _get_auth_header(
        client,
        course_setup["prof2"].email,
        course_setup["password"],
    )
    student_header = await _get_auth_header(
        client,
        course_setup["student1"].email,
        course_setup["password"],
    )

    # Prof 1 creates course
    c_resp = await client.post(
        "/api/v1/courses",
        json={"code": "BIO101", "title": "Biology", "term": "2026-autumn"},
        headers=prof1_header,
    )
    course_id = c_resp.json()["id"]

    # Student attempts to patch -> 403
    student_patch = await client.patch(
        f"/api/v1/courses/{course_id}",
        json={"title": "Hacked Biology"},
        headers=student_header,
    )
    assert student_patch.status_code == 403

    # Other professor (Prof 2) attempts to patch -> 403
    prof2_patch = await client.patch(
        f"/api/v1/courses/{course_id}",
        json={"title": "Stolen Biology"},
        headers=prof2_header,
    )
    assert prof2_patch.status_code == 403

    # Owning professor (Prof 1) patches course -> 200
    owner_patch = await client.patch(
        f"/api/v1/courses/{course_id}",
        json={"title": "Advanced Biology", "archived": True},
        headers=prof1_header,
    )
    assert owner_patch.status_code == 200
    assert owner_patch.json()["title"] == "Advanced Biology"
    assert owner_patch.json()["archived"] is True


@pytest.mark.asyncio
async def test_enrollments_email_list_and_unknowns(
    client: AsyncClient,
    db_session: AsyncSession,
    course_setup: dict[str, Any],
) -> None:
    """Batch enroll by email list creates enrollments for known users and reports unknown."""
    prof1_header = await _get_auth_header(
        client,
        course_setup["prof1"].email,
        course_setup["password"],
    )

    c_resp = await client.post(
        "/api/v1/courses",
        json={"code": "CHEM101", "title": "Chemistry", "term": "2026-autumn"},
        headers=prof1_header,
    )
    course_id = c_resp.json()["id"]

    # Enroll: 1 known student, 1 unknown email
    unknown_email = "ghost@campus.local"
    enroll_resp = await client.post(
        f"/api/v1/courses/{course_id}/enrollments",
        json={
            "emails": [course_setup["student1"].email, unknown_email],
            "role": "student",
        },
        headers=prof1_header,
    )
    assert enroll_resp.status_code == 200
    data = enroll_resp.json()
    assert len(data["added"]) == 1
    assert data["added"][0]["email"] == course_setup["student1"].email
    assert data["unknown"] == [unknown_email]

    # Verify that unknown user was NOT created in users table
    stmt = select(User).where(User.email == unknown_email)
    ghost_user = (await db_session.execute(stmt)).scalar_one_or_none()
    assert ghost_user is None

    # Re-enrolling the same student reports them in already_enrolled
    re_enroll = await client.post(
        f"/api/v1/courses/{course_id}/enrollments",
        json={"emails": [course_setup["student1"].email]},
        headers=prof1_header,
    )
    assert re_enroll.status_code == 200
    re_data = re_enroll.json()
    assert len(re_data["added"]) == 0
    assert len(re_data["already_enrolled"]) == 1
    assert re_data["already_enrolled"][0]["email"] == course_setup["student1"].email


@pytest.mark.asyncio
async def test_enrollments_csv_upload(
    client: AsyncClient,
    db_session: AsyncSession,
    course_setup: dict[str, Any],
) -> None:
    """Batch enroll via CSV file upload parses emails and identifies unknown."""
    prof1_header = await _get_auth_header(
        client,
        course_setup["prof1"].email,
        course_setup["password"],
    )

    c_resp = await client.post(
        "/api/v1/courses",
        json={"code": "ENG101", "title": "Literature", "term": "2026-autumn"},
        headers=prof1_header,
    )
    course_id = c_resp.json()["id"]

    csv_content = (
        "Name,Email\n"
        f"Student Two,{course_setup['student2'].email}\n"
        "Ghost Person,ghost_csv@campus.local\n"
    )

    files = {"file": ("students.csv", csv_content.encode("utf-8"), "text/csv")}
    upload_resp = await client.post(
        f"/api/v1/courses/{course_id}/enrollments",
        files=files,
        headers=prof1_header,
    )
    assert upload_resp.status_code == 200
    data = upload_resp.json()
    assert len(data["added"]) == 1
    assert data["added"][0]["email"] == course_setup["student2"].email
    assert data["unknown"] == ["ghost_csv@campus.local"]

    # Ensure ghost_csv was not inserted into users table
    stmt = select(User).where(User.email == "ghost_csv@campus.local")
    ghost_user = (await db_session.execute(stmt)).scalar_one_or_none()
    assert ghost_user is None


@pytest.mark.asyncio
async def test_remove_enrollment(
    client: AsyncClient,
    course_setup: dict[str, Any],
) -> None:
    """Owner can delete an enrollment; non-owner cannot."""
    prof1_header = await _get_auth_header(
        client,
        course_setup["prof1"].email,
        course_setup["password"],
    )
    student1_header = await _get_auth_header(
        client,
        course_setup["student1"].email,
        course_setup["password"],
    )

    # Prof 1 creates course and enrolls Student 1
    c_resp = await client.post(
        "/api/v1/courses",
        json={"code": "HIST101", "title": "World History", "term": "2026-autumn"},
        headers=prof1_header,
    )
    course_id = c_resp.json()["id"]
    student_id = course_setup["student1"].id

    await client.post(
        f"/api/v1/courses/{course_id}/enrollments",
        json={"emails": [course_setup["student1"].email]},
        headers=prof1_header,
    )

    # Student cannot remove themselves or others -> 403
    student_del = await client.delete(
        f"/api/v1/courses/{course_id}/enrollments/{student_id}",
        headers=student1_header,
    )
    assert student_del.status_code == 403

    # Owner removes student -> 200
    owner_del = await client.delete(
        f"/api/v1/courses/{course_id}/enrollments/{student_id}",
        headers=prof1_header,
    )
    assert owner_del.status_code == 200
    assert owner_del.json() == {"status": "ok"}

    # Student is no longer enrolled -> 403 on detail
    detail_resp = await client.get(
        f"/api/v1/courses/{course_id}",
        headers=student1_header,
    )
    assert detail_resp.status_code == 403
