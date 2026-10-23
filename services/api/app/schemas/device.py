"""Schemas for devices and offline license renewal."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DeviceCreate(BaseModel):
    """Device registration payload."""

    name: str = Field(..., min_length=1, max_length=100)
    public_key: str = Field(..., min_length=1)


class DeviceOut(BaseModel):
    """Public device record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    public_key: str
    created_at: datetime
    revoked_at: datetime | None = None


class LicenseRenewRequest(BaseModel):
    """License renewal request payload."""

    device_id: uuid.UUID


class RenewedLicenseOut(BaseModel):
    """Renewed license item."""

    lecture_id: uuid.UUID
    token: str
    expires_at: datetime


class LicenseRenewResponse(BaseModel):
    """License renewal outcome listing renewed tokens and revoked lecture ids."""

    device_id: uuid.UUID
    renewed: list[RenewedLicenseOut]
    revoked: list[uuid.UUID]


class LicensePublicKeyResponse(BaseModel):
    """Public key for client-side license verification."""

    public_key: str
    algorithm: str = "Ed25519"
