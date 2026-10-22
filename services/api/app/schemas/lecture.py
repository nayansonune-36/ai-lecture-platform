"""Pydantic schemas for lectures, uploads, and jobs."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import JobStatus, JobType, LectureStatus


class LectureCreate(BaseModel):
    """Schema for creating a lecture placeholder and initiating upload."""

    title: str
    filename: str
    description: str | None = None
    position: int | None = None
    primary_language: str | None = None


class LectureUpdate(BaseModel):
    """Schema for updating lecture details."""

    title: str | None = None
    description: str | None = None
    position: int | None = None
    published: bool | None = None
    primary_language: str | None = None


class LectureOut(BaseModel):
    """Public lecture detail schema."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    description: str | None
    position: int
    status: LectureStatus
    published: bool
    duration_ms: int | None
    primary_language: str | None
    original_path: str
    hls_master_path: str | None
    poster_path: str | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class LectureCreateResponse(BaseModel):
    """Response after creating lecture record, including resumable upload URL."""

    lecture: LectureOut
    upload_url: str


class ChunkUploadResponse(BaseModel):
    """Response returned after uploading a file chunk."""

    bytes_written: int
    current_size: int
    total_size: int | None = None
    status: str = "incomplete"


class UploadCompleteResponse(BaseModel):
    """Response after completing upload and queuing processing."""

    status: str = "processing"
    job_id: uuid.UUID
    lecture: LectureOut


class JobOut(BaseModel):
    """Job status record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lecture_id: uuid.UUID | None
    type: JobType
    status: JobStatus
    attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
