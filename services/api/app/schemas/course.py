"""Pydantic schemas for courses and enrollments."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import EnrollmentRole


class CourseCreate(BaseModel):
    """Schema for creating a new course."""

    code: str
    title: str
    description: str | None = None
    term: str | None = None


class CourseUpdate(BaseModel):
    """Schema for updating an existing course."""

    title: str | None = None
    description: str | None = None
    term: str | None = None
    archived: bool | None = None


class CourseOut(BaseModel):
    """Public course details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    title: str
    description: str | None
    term: str | None
    owner_id: uuid.UUID
    archived: bool
    created_at: datetime


class EnrollmentMemberOut(BaseModel):
    """Member detail within a course enrollment list."""

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    email: str
    name: str
    role: EnrollmentRole
    created_at: datetime


class EnrollmentAddRequest(BaseModel):
    """JSON payload for adding enrollments by email list."""

    emails: list[str] = []
    role: EnrollmentRole = EnrollmentRole.STUDENT


class EnrollmentAddResponse(BaseModel):
    """Result of batch enrollment creation."""

    added: list[EnrollmentMemberOut]
    already_enrolled: list[EnrollmentMemberOut]
    unknown: list[str]


class StatusResponse(BaseModel):
    """Generic status response."""

    status: str = "ok"
