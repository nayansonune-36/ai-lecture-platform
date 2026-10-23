"""Tests for SQLAlchemy models and metadata reflection."""

import uuid

from app.db import Base
from app.models import (
    Bundle,
    Course,
    Enrollment,
    EnrollmentRole,
    Job,
    JobStatus,
    JobType,
    Lecture,
    LectureRendition,
    LectureStatus,
    PlaybackProgress,
    User,
    UserRole,
)


def test_metadata_contains_required_tables() -> None:
    """Verify that all Phase 1 required tables are defined in metadata."""
    expected_tables = {
        "users",
        "courses",
        "enrollments",
        "lectures",
        "lecture_renditions",
        "playback_progress",
        "jobs",
        "bundles",
    }
    registered_tables = set(Base.metadata.tables.keys())
    assert expected_tables.issubset(registered_tables), (
        f"Missing tables: {expected_tables - registered_tables}"
    )


def test_users_table_structure() -> None:
    table = Base.metadata.tables["users"]
    assert "id" in table.c
    assert "email" in table.c
    assert "name" in table.c
    assert "role" in table.c
    assert "password_hash" in table.c
    assert "sso_subject" in table.c
    assert "is_active" in table.c
    assert "created_at" in table.c
    assert table.c.id.primary_key is True


def test_courses_table_structure() -> None:
    table = Base.metadata.tables["courses"]
    assert "id" in table.c
    assert "code" in table.c
    assert "title" in table.c
    assert "term" in table.c
    assert "owner_id" in table.c
    assert "archived" in table.c
    uq_names = [uq.name for uq in table.constraints if hasattr(uq, "columns")]
    assert "courses_code_term_uq" in uq_names


def test_enrollments_table_structure() -> None:
    table = Base.metadata.tables["enrollments"]
    assert "course_id" in table.c
    assert "user_id" in table.c
    assert "role" in table.c
    assert table.c.course_id.primary_key is True
    assert table.c.user_id.primary_key is True


def test_lectures_table_structure() -> None:
    table = Base.metadata.tables["lectures"]
    assert "id" in table.c
    assert "course_id" in table.c
    assert "title" in table.c
    assert "position" in table.c
    assert "status" in table.c
    assert "published" in table.c
    assert "duration_ms" in table.c
    assert "original_path" in table.c
    assert "created_by" in table.c


def test_lecture_renditions_table_structure() -> None:
    table = Base.metadata.tables["lecture_renditions"]
    assert "id" in table.c
    assert "lecture_id" in table.c
    assert "height" in table.c
    assert "bitrate_kbps" in table.c
    assert "playlist_path" in table.c
    uq_names = [uq.name for uq in table.constraints if hasattr(uq, "columns")]
    assert "lecture_renditions_lecture_height_uq" in uq_names


def test_playback_progress_table_structure() -> None:
    table = Base.metadata.tables["playback_progress"]
    assert "user_id" in table.c
    assert "lecture_id" in table.c
    assert "position_ms" in table.c
    assert "completed" in table.c
    assert table.c.user_id.primary_key is True
    assert table.c.lecture_id.primary_key is True


def test_jobs_table_structure() -> None:
    table = Base.metadata.tables["jobs"]
    assert "id" in table.c
    assert "lecture_id" in table.c
    assert "type" in table.c
    assert "status" in table.c
    assert "payload" in table.c
    assert "error" in table.c
    assert "attempts" in table.c


def test_model_instantiation() -> None:
    uid = uuid.uuid4()
    cid = uuid.uuid4()
    lid = uuid.uuid4()

    user = User(id=uid, email="test@test.local", name="Test", role=UserRole.STUDENT)
    course = Course(id=cid, code="CS101", title="Intro to CS", owner_id=uid)
    enrollment = Enrollment(course_id=cid, user_id=uid, role=EnrollmentRole.STUDENT)
    lecture = Lecture(
        id=lid,
        course_id=cid,
        title="Lecture 1",
        original_path="lectures/1/raw.mp4",
        created_by=uid,
        status=LectureStatus.UPLOADED,
    )
    rendition = LectureRendition(
        lecture_id=lid,
        height=720,
        bitrate_kbps=2500,
        playlist_path="720p.m3u8",
    )
    progress = PlaybackProgress(user_id=uid, lecture_id=lid, position_ms=1000)
    job = Job(lecture_id=lid, type=JobType.TRANSCODE, status=JobStatus.QUEUED)
    bundle = Bundle(
        lecture_id=lid,
        rendition=480,
        version=1,
        path="bundles/test/480p-v1.zip",
        size_bytes=1000000,
        sha256="abc123sha",
    )

    assert user.role == UserRole.STUDENT
    assert course.code == "CS101"
    assert enrollment.role == EnrollmentRole.STUDENT
    assert lecture.status == LectureStatus.UPLOADED
    assert rendition.height == 720
    assert progress.position_ms == 1000
    assert job.type == JobType.TRANSCODE
    assert bundle.rendition == 480
    assert bundle.version == 1
