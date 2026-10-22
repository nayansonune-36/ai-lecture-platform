"""Courses and enrollments router."""

import uuid

from fastapi import APIRouter, Body, Depends, Path, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.db import get_db
from app.deps import get_current_user, require_role
from app.models.enums import EnrollmentRole, UserRole
from app.models.user import User
from app.schemas.course import (
    CourseCreate,
    CourseOut,
    CourseUpdate,
    EnrollmentAddResponse,
    EnrollmentMemberOut,
    StatusResponse,
)
from app.services.course_service import (
    add_course_enrollments,
    create_course,
    get_course_detail,
    get_user_courses,
    list_course_enrollments,
    parse_emails_from_csv,
    remove_course_enrollment,
    update_course,
)

router = APIRouter(tags=["courses"])

_require_professor = require_role(UserRole.PROFESSOR, UserRole.ADMIN)


@router.get(
    "/courses",
    response_model=list[CourseOut],
    summary="List courses for current user",
    description="Retrieve all courses the current user owns or is enrolled in.",
)
async def list_courses(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CourseOut]:
    courses = await get_user_courses(db=db, user=current_user)
    return [CourseOut.model_validate(c) for c in courses]


@router.post(
    "/courses",
    response_model=CourseOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new course",
    description="Professors or administrators can create new courses.",
)
async def create_new_course(
    payload: CourseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_professor),
) -> CourseOut:
    course = await create_course(db=db, user=current_user, data=payload)
    return CourseOut.model_validate(course)


@router.get(
    "/courses/{id}",
    response_model=CourseOut,
    summary="Get course details",
    description="Retrieve course detail for enrolled students, instructors, or admins.",
)
async def get_course(
    course_id: uuid.UUID = Path(..., alias="id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CourseOut:
    course = await get_course_detail(db=db, course_id=course_id, user=current_user)
    return CourseOut.model_validate(course)


@router.patch(
    "/courses/{id}",
    response_model=CourseOut,
    summary="Update a course",
    description="Course owners or administrators can edit course metadata or archive the course.",
)
async def patch_course(
    course_id: uuid.UUID = Path(..., alias="id"),
    payload: CourseUpdate = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CourseOut:
    course = await update_course(
        db=db,
        course_id=course_id,
        user=current_user,
        data=payload,
    )
    return CourseOut.model_validate(course)


@router.get(
    "/courses/{id}/enrollments",
    response_model=list[EnrollmentMemberOut],
    summary="List course enrollments",
    description="Course owner or administrator can view all enrolled members.",
)
async def get_enrollments(
    course_id: uuid.UUID = Path(..., alias="id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EnrollmentMemberOut]:
    return await list_course_enrollments(db=db, course_id=course_id, user=current_user)


@router.post(
    "/courses/{id}/enrollments",
    response_model=EnrollmentAddResponse,
    summary="Enroll members by email list or CSV",
    description="Batch enroll users via JSON email list or CSV file upload.",
)
async def add_enrollments(
    request: Request,
    course_id: uuid.UUID = Path(..., alias="id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EnrollmentAddResponse:
    content_type = request.headers.get("content-type", "")
    emails: list[str] = []
    role = EnrollmentRole.STUDENT

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        uploaded_file = form.get("file")
        if uploaded_file is None or not hasattr(uploaded_file, "read"):
            raise ApiError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="bad_request",
                message="CSV file is required in multipart form field 'file'",
            )
        content_bytes = await uploaded_file.read()
        csv_text = content_bytes.decode("utf-8", errors="replace")
        emails = parse_emails_from_csv(csv_text)

        form_role = form.get("role")
        if isinstance(form_role, str) and form_role in EnrollmentRole:
            role = EnrollmentRole(form_role)
    else:
        try:
            body = await request.json()
        except Exception:
            body = {}
        emails = body.get("emails", [])
        raw_role = body.get("role", "student")
        if isinstance(raw_role, str) and raw_role in EnrollmentRole:
            role = EnrollmentRole(raw_role)

    return await add_course_enrollments(
        db=db,
        course_id=course_id,
        user=current_user,
        emails=emails,
        role=role,
    )


@router.delete(
    "/courses/{id}/enrollments/{user_id}",
    response_model=StatusResponse,
    summary="Remove a course member",
    description="Remove an enrollment and revoke associated offline licenses.",
)
async def delete_enrollment(
    course_id: uuid.UUID = Path(..., alias="id"),
    user_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StatusResponse:
    await remove_course_enrollment(
        db=db,
        course_id=course_id,
        member_id=user_id,
        user=current_user,
    )
    return StatusResponse(status="ok")
