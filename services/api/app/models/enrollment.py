"""Course enrollment model definition."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import EnrollmentRole

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.user import User


class Enrollment(Base):
    """User course enrollment entity."""

    __tablename__ = "enrollments"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[EnrollmentRole] = mapped_column(
        Enum(
            EnrollmentRole,
            name="enrollment_role",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=EnrollmentRole.STUDENT,
        server_default=text("'student'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )

    # Relationships
    course: Mapped["Course"] = relationship(
        "Course",
        back_populates="enrollments",
    )
    user: Mapped["User"] = relationship(
        "User",
        back_populates="enrollments",
    )

    __table_args__ = (Index("enrollments_user_idx", "user_id"),)
