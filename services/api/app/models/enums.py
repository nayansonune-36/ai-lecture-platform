"""Enum types reflecting docs/schema.sql."""

import enum


class UserRole(enum.StrEnum):
    """User roles within the platform."""

    STUDENT = "student"
    PROFESSOR = "professor"
    ADMIN = "admin"


class EnrollmentRole(enum.StrEnum):
    """Enrollment roles within a specific course."""

    STUDENT = "student"
    TA = "ta"
    INSTRUCTOR = "instructor"


class LectureStatus(enum.StrEnum):
    """Lifecycle status of an uploaded lecture."""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class JobType(enum.StrEnum):
    """Types of background processing jobs."""

    TRANSCODE = "transcode"
    TRANSCRIBE = "transcribe"
    INDEX = "index"
    CHAPTERS = "chapters"
    BUNDLE = "bundle"


class JobStatus(enum.StrEnum):
    """Execution status of background jobs."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChatRole(enum.StrEnum):
    """Role in AI tutor chat sessions."""

    USER = "user"
    ASSISTANT = "assistant"
