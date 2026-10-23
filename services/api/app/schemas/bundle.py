"""Schemas for offline bundles and estimation."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class OfflineEstimateResponse(BaseModel):
    """Estimated bundle download size in bytes."""

    lecture_id: uuid.UUID
    rendition: int
    estimated_size_bytes: int


class OfflineBundleRequest(BaseModel):
    """Request payload to queue or retrieve offline bundle."""

    device_id: uuid.UUID | None = None
    rendition: int = Field(default=480, description="Rendition height (720, 480, 360)")


class OfflineBundleResponse(BaseModel):
    """Status, download URL, metadata, and license token for an offline bundle."""

    job_id: uuid.UUID
    status: str
    bundle_id: uuid.UUID | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    download_url: str | None = None
    license_token: str | None = None
    expires_at: datetime | None = None
