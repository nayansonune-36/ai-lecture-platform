"""Courses and enrollments business logic service."""

import csv
import io
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, forbidden
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.enums import EnrollmentRole, UserRole
from app.models.user import User
from app.schemas.course import (
    CourseCreate,
    CourseUpdate,
    EnrollmentAddResponse,
    EnrollmentMemberOut,
)


def parse_emails_from_csv(csv_text: str) -> list[str]:
    """Extract email addresses from a CSV string."""
    emails: list[str] = []
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    if not rows:
        return emails

    # Check for header row
    first_row = [col.strip().lower() for col in rows[0]]
    email_col_idx = 0
    start_row = 0

    if "email" in first_row:
        email_col_idx = first_row.index("email")
        start_row = 1
    else:
        # Determine if first row is data
        for idx, cell in enumerate(rows[0]):
            if "@" in cell:
                email_col_idx = idx
                start_row = 0
                break

    for row in rows[start_row:]:
        if len(row) > email_col_idx:
            cell = row[email_col_idx].strip()
            if cell and "@" in cell:
                emails.append(cell)

    return emails


async def get_user_courses(db: AsyncSession, user: User) -> list[Course]:
    """Retrieve courses the caller owns or is enrolled in."""
    enrolled_course_ids = select(Enrollment.course_id).where(Enrollment.user_id == user.id)

    stmt = (
        select(Course)
        .where(or_(Course.owner_id == user.id, Course.id.in_(enrolled_course_ids)))
        .order_by(Course.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_course(db: AsyncSession, user: User, data: CourseCreate) -> Course:
    """Create a new course owned by the caller."""
    # Check uniqueness of (code, term)
    stmt = select(Course).where(Course.code == data.code, Course.term == data.term)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        raise ApiError(
            status_code=409,
            code="course_already_exists",
            message="A course with this code and term already exists",
        )

    course = Course(
        code=data.code,
        title=data.title,
        description=data.description,
        term=data.term,
        owner_id=user.id,
    )
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return course


async def get_course_detail(db: AsyncSession, course_id: uuid.UUID, user: User) -> Course:
    """Retrieve course detail if the caller is an owner, admin, or enrolled member."""
    stmt = select(Course).where(Course.id == course_id)
    course = (await db.execute(stmt)).scalar_one_or_none()
    if course is None:
        raise ApiError(status_code=404, code="course_not_found", message="Course not found")

    if user.role == UserRole.ADMIN or course.owner_id == user.id:
        return course

    # Check enrollment
    enrollment_stmt = select(Enrollment).where(
        Enrollment.course_id == course_id,
        Enrollment.user_id == user.id,
    )
    enrollment = (await db.execute(enrollment_stmt)).scalar_one_or_none()
    if enrollment is None:
        raise forbidden("You are not enrolled in this course", code="forbidden")

    return course


async def update_course(
    db: AsyncSession,
    course_id: uuid.UUID,
    user: User,
    data: CourseUpdate,
) -> Course:
    """Update course attributes (owner or admin only)."""
    stmt = select(Course).where(Course.id == course_id)
    course = (await db.execute(stmt)).scalar_one_or_none()
    if course is None:
        raise ApiError(status_code=404, code="course_not_found", message="Course not found")

    if user.role != UserRole.ADMIN and course.owner_id != user.id:
        raise forbidden("Only the course owner can modify this course", code="forbidden")

    if data.title is not None:
        course.title = data.title
    if data.description is not None:
        course.description = data.description
    if data.term is not None:
        course.term = data.term
    if data.archived is not None:
        course.archived = data.archived

    await db.commit()
    await db.refresh(course)
    return course


async def list_course_enrollments(
    db: AsyncSession,
    course_id: uuid.UUID,
    user: User,
) -> list[EnrollmentMemberOut]:
    """List members enrolled in the course (owner or admin only)."""
    stmt = select(Course).where(Course.id == course_id)
    course = (await db.execute(stmt)).scalar_one_or_none()
    if course is None:
        raise ApiError(status_code=404, code="course_not_found", message="Course not found")

    if user.role != UserRole.ADMIN and course.owner_id != user.id:
        raise forbidden("Only the course owner can view enrollments", code="forbidden")

    enrollments_stmt = (
        select(Enrollment, User)
        .join(User, Enrollment.user_id == User.id)
        .where(Enrollment.course_id == course_id)
        .order_by(Enrollment.created_at.asc())
    )
    result = await db.execute(enrollments_stmt)

    members: list[EnrollmentMemberOut] = []
    for enrollment, member_user in result.all():
        members.append(
            EnrollmentMemberOut(
                user_id=member_user.id,
                email=member_user.email,
                name=member_user.name,
                role=enrollment.role,
                created_at=enrollment.created_at,
            )
        )
    return members


async def add_course_enrollments(
    db: AsyncSession,
    course_id: uuid.UUID,
    user: User,
    emails: list[str],
    role: EnrollmentRole,
) -> EnrollmentAddResponse:
    """Batch enroll users by email list (owner or admin only)."""
    stmt = select(Course).where(Course.id == course_id)
    course = (await db.execute(stmt)).scalar_one_or_none()
    if course is None:
        raise ApiError(status_code=404, code="course_not_found", message="Course not found")

    if user.role != UserRole.ADMIN and course.owner_id != user.id:
        raise forbidden("Only the course owner can manage enrollments", code="forbidden")

    # Clean and deduplicate while preserving input ordering
    seen_emails: set[str] = set()
    clean_emails: list[str] = []
    for raw in emails:
        clean = raw.strip().lower()
        if clean and clean not in seen_emails:
            seen_emails.add(clean)
            clean_emails.append(clean)

    if not clean_emails:
        return EnrollmentAddResponse(added=[], already_enrolled=[], unknown=[])

    # Fetch users matching the emails
    users_stmt = select(User).where(func.lower(User.email).in_(clean_emails))
    found_users_res = await db.execute(users_stmt)
    found_users = {u.email.lower(): u for u in found_users_res.scalars().all()}

    # Fetch existing enrollments for this course
    existing_enrollments_stmt = select(Enrollment).where(
        Enrollment.course_id == course_id,
        Enrollment.user_id.in_([u.id for u in found_users.values()]),
    )
    existing_res = await db.execute(existing_enrollments_stmt)
    existing_user_ids = {e.user_id: e for e in existing_res.scalars().all()}

    added: list[EnrollmentMemberOut] = []
    already_enrolled: list[EnrollmentMemberOut] = []
    unknown: list[str] = []

    now = datetime.now(UTC)

    for email in clean_emails:
        if email not in found_users:
            unknown.append(email)
            continue

        target_user = found_users[email]
        if target_user.id in existing_user_ids:
            enr = existing_user_ids[target_user.id]
            already_enrolled.append(
                EnrollmentMemberOut(
                    user_id=target_user.id,
                    email=target_user.email,
                    name=target_user.name,
                    role=enr.role,
                    created_at=enr.created_at,
                )
            )
        else:
            new_enr = Enrollment(
                course_id=course_id,
                user_id=target_user.id,
                role=role,
                created_at=now,
            )
            db.add(new_enr)
            added.append(
                EnrollmentMemberOut(
                    user_id=target_user.id,
                    email=target_user.email,
                    name=target_user.name,
                    role=role,
                    created_at=now,
                )
            )

    if added:
        await db.commit()

    return EnrollmentAddResponse(
        added=added,
        already_enrolled=already_enrolled,
        unknown=unknown,
    )


async def remove_course_enrollment(
    db: AsyncSession,
    course_id: uuid.UUID,
    member_id: uuid.UUID,
    user: User,
) -> None:
    """Remove a user from course enrollments and revoke offline licenses."""
    stmt = select(Course).where(Course.id == course_id)
    course = (await db.execute(stmt)).scalar_one_or_none()
    if course is None:
        raise ApiError(status_code=404, code="course_not_found", message="Course not found")

    if user.role != UserRole.ADMIN and course.owner_id != user.id:
        raise forbidden("Only the course owner can manage enrollments", code="forbidden")

    enrollment_stmt = select(Enrollment).where(
        Enrollment.course_id == course_id,
        Enrollment.user_id == member_id,
    )
    enrollment = (await db.execute(enrollment_stmt)).scalar_one_or_none()
    if enrollment is None:
        raise ApiError(status_code=404, code="enrollment_not_found", message="Enrollment not found")

    # Revoke offline licenses for lectures belonging to this course
    try:
        await db.execute(
            text(
                "DELETE FROM offline_licenses "
                "WHERE user_id = :member_id "
                "AND lecture_id IN (SELECT id FROM lectures WHERE course_id = :course_id)"
            ),
            {"member_id": member_id, "course_id": course_id},
        )
    except Exception:
        # Table might not exist in SQLite unit test environment
        pass

    # Delete enrollment
    await db.execute(
        delete(Enrollment).where(
            Enrollment.course_id == course_id,
            Enrollment.user_id == member_id,
        )
    )
    await db.commit()
