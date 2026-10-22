"""User model definition."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Index, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.enrollment import Enrollment
    from app.models.lecture import Lecture
    from app.models.playback import PlaybackProgress


class User(Base):
    """User account entity."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=True),
        nullable=False,
        default=UserRole.STUDENT,
        server_default=text("'student'"),
    )
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    sso_subject: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )

    # Relationships
    courses_owned: Mapped[list["Course"]] = relationship(
        "Course",
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    enrollments: Mapped[list["Enrollment"]] = relationship(
        "Enrollment",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    lectures_created: Mapped[list["Lecture"]] = relationship(
        "Lecture",
        back_populates="creator",
    )
    playback_progress: Mapped[list["PlaybackProgress"]] = relationship(
        "PlaybackProgress",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    __table_args__ = (Index("users_email_lower_uq", func.lower(email), unique=True),)
