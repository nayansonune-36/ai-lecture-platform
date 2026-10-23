"""Database models and enums for ARQ worker."""

import enum
import uuid
from datetime import datetime
from typing import Any

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
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from db import Base


class JobType(enum.StrEnum):
    """Background job task type."""

    TRANSCODE = "transcode"
    TRANSCRIBE = "transcribe"
    INDEX = "index"
    CHAPTERS = "chapters"
    BUNDLE = "bundle"


class JobStatus(enum.StrEnum):
    """Background job processing status."""

    QUEUED = "queued"
    RUNNING = "running"
    PROCESSING = "running"
    SUCCEEDED = "succeeded"
    COMPLETED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Course(Base):
    """Course catalog entity."""

    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    term: Mapped[str | None] = mapped_column(Text, nullable=True)


class LectureStatus(enum.StrEnum):
    """Lecture processing and readiness status."""

    DRAFT = "draft"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Lecture(Base):
    """Lecture model representing university media asset."""

    __tablename__ = "lectures"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_path: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    language: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[LectureStatus] = mapped_column(
        Enum(LectureStatus, name="lecture_status", native_enum=False),
        nullable=False,
        default=LectureStatus.DRAFT,
    )
    published: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    hls_master_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    poster_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
    )

    course: Mapped["Course | None"] = relationship("Course")
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
    bundles: Mapped[list["Bundle"]] = relationship(
        "Bundle",
        back_populates="lecture",
        cascade="all, delete-orphan",
    )


class LectureRendition(Base):
    """Rendition profile for adaptive HLS streaming."""

    __tablename__ = "lecture_renditions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    lecture_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("lectures.id", ondelete="CASCADE"),
        nullable=False,
    )
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    bitrate_kbps: Mapped[int] = mapped_column(Integer, nullable=False)
    playlist_path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    lecture: Mapped["Lecture"] = relationship(
        "Lecture",
        back_populates="renditions",
    )

    __table_args__ = (
        UniqueConstraint("lecture_id", "height", name="uq_lecture_renditions_lecture_height"),
    )


class Job(Base):
    """Durable record of background job execution."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    lecture_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("lectures.id", ondelete="CASCADE"),
        nullable=True,
    )
    type: Mapped[JobType] = mapped_column(
        Enum(JobType, name="job_type", native_enum=False),
        nullable=False,
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", native_enum=False),
        nullable=False,
        default=JobStatus.QUEUED,
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    lecture: Mapped["Lecture | None"] = relationship(
        "Lecture",
        back_populates="jobs",
    )

    __table_args__ = (
        Index("jobs_lecture_idx", "lecture_id", "type"),
        Index("jobs_status_idx", "status", "created_at"),
    )


class Bundle(Base):
    """Offline lecture bundle package."""

    __tablename__ = "bundles"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    lecture_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("lectures.id", ondelete="CASCADE"),
        nullable=False,
    )
    rendition: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
    )

    lecture: Mapped["Lecture"] = relationship(
        "Lecture",
        back_populates="bundles",
    )

    __table_args__ = (
        UniqueConstraint(
            "lecture_id", "rendition", "version", name="bundles_lecture_rendition_version_uq"
        ),
        Index("bundles_lecture_rendition_idx", "lecture_id", "rendition"),
    )


class Chapter(Base):
    """Chapter markers for video playback."""

    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lecture_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("lectures.id", ondelete="CASCADE"),
        nullable=False,
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("lecture_id", "idx", name="chapters_lecture_idx_uq"),
    )


class TranscriptSegment(Base):
    """Transcript segment for generating VTT captions."""

    __tablename__ = "transcript_segments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lecture_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("lectures.id", ondelete="CASCADE"),
        nullable=False,
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    lang: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("lecture_id", "idx", name="transcript_segments_lecture_idx_uq"),
    )

