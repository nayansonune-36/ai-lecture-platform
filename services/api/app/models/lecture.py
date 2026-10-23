"""Lecture and rendition models."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import LectureStatus

if TYPE_CHECKING:
    from app.models.bundle import Bundle
    from app.models.course import Course
    from app.models.job import Job
    from app.models.playback import PlaybackProgress
    from app.models.user import User


class Lecture(Base):
    """Lecture media and metadata entity."""

    __tablename__ = "lectures"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    status: Mapped[LectureStatus] = mapped_column(
        Enum(LectureStatus, name="lecture_status", native_enum=True),
        nullable=False,
        default=LectureStatus.UPLOADED,
        server_default=text("'uploaded'"),
    )
    published: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    primary_language: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_path: Mapped[str] = mapped_column(Text, nullable=False)
    hls_master_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    poster_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    course: Mapped["Course"] = relationship(
        "Course",
        back_populates="lectures",
    )
    creator: Mapped["User"] = relationship(
        "User",
        back_populates="lectures_created",
    )
    renditions: Mapped[list["LectureRendition"]] = relationship(
        "LectureRendition",
        back_populates="lecture",
        cascade="all, delete-orphan",
    )
    jobs: Mapped[list["Job"]] = relationship(
        "Job",
        back_populates="lecture",
        cascade="all, delete-orphan",
    )
    playback_progress: Mapped[list["PlaybackProgress"]] = relationship(
        "PlaybackProgress",
        back_populates="lecture",
        cascade="all, delete-orphan",
    )
    bundles: Mapped[list["Bundle"]] = relationship(
        "Bundle",
        back_populates="lecture",
        cascade="all, delete-orphan",
    )

    __table_args__ = (Index("lectures_course_idx", "course_id", "position"),)


class LectureRendition(Base):
    """Specific video rendition (resolution and bitrate) for a lecture."""

    __tablename__ = "lecture_renditions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    lecture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lectures.id", ondelete="CASCADE"),
        nullable=False,
    )
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    bitrate_kbps: Mapped[int] = mapped_column(Integer, nullable=False)
    playlist_path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Relationships
    lecture: Mapped["Lecture"] = relationship(
        "Lecture",
        back_populates="renditions",
    )

    __table_args__ = (
        UniqueConstraint("lecture_id", "height", name="lecture_renditions_lecture_height_uq"),
    )
