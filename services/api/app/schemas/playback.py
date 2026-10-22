"""Playback and progress schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class PlaybackTokenResponse(BaseModel):
    """Signed manifest URL and expiration timestamp."""

    manifest_url: str = Field(..., description="Signed URL to HLS master playlist")
    expires_at: datetime = Field(..., description="Token expiration timestamp")


class ChapterOut(BaseModel):
    """Lecture chapter marker."""

    start_ms: int = Field(..., description="Start position in milliseconds")
    title: str = Field(..., description="Chapter title")
    summary: str | None = Field(None, description="Optional chapter summary")


class PlaybackProgressOut(BaseModel):
    """Playback resume position and completion state."""

    position_ms: int = Field(0, description="Saved playback position in milliseconds")
    completed: bool = Field(False, description="Whether playback was completed")


class PlaybackProgressUpdate(BaseModel):
    """Payload to update playback progress position."""

    position_ms: int = Field(..., ge=0, description="Current playback position in milliseconds")
    completed: bool = Field(False, description="Whether lecture is completed")
