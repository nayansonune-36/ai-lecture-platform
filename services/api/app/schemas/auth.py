"""Authentication request and response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import UserRole


class UserOut(BaseModel):
    """Public user representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class LoginRequest(BaseModel):
    """User login request payload."""

    email: str
    password: str


class LoginResponse(BaseModel):
    """Successful login response payload."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = 900
    refresh_token: str
    user: UserOut


class RefreshRequest(BaseModel):
    """Refresh token request payload."""

    refresh_token: str


class RefreshResponse(BaseModel):
    """Rotated token response payload."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = 900
    refresh_token: str


class LogoutRequest(BaseModel):
    """Logout request payload."""

    refresh_token: str | None = None


class LogoutResponse(BaseModel):
    """Logout response payload."""

    status: str = "ok"
