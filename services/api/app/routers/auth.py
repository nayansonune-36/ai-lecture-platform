"""Authentication and user profile router."""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.db import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    LogoutResponse,
    RefreshRequest,
    RefreshResponse,
    UserOut,
)
from app.services.auth import (
    authenticate_user,
    revoke_refresh_token,
    rotate_refresh_token,
)

router = APIRouter(tags=["auth"])


def get_client_ip(request: Request) -> str:
    """Extract real client IP considering forward headers from proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"


@router.post(
    "/auth/login",
    response_model=LoginResponse,
    summary="User login",
    description="Authenticate user with email and password, returning access and refresh tokens.",
)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    client_ip = get_client_ip(request)
    user, access_token, refresh_token = await authenticate_user(
        db=db,
        email=payload.email,
        password=payload.password,
        client_ip=client_ip,
    )
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=900,
        refresh_token=refresh_token,
        user=UserOut.model_validate(user),
    )


@router.post(
    "/auth/refresh",
    response_model=RefreshResponse,
    summary="Rotate refresh token",
    description="Exchange a valid refresh token for a new access token and rotated refresh token.",
)
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> RefreshResponse:
    new_access_token, new_refresh_token = await rotate_refresh_token(
        db=db,
        raw_refresh_token=payload.refresh_token,
    )
    return RefreshResponse(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=900,
        refresh_token=new_refresh_token,
    )


@router.post(
    "/auth/logout",
    response_model=LogoutResponse,
    summary="User logout",
    description="Revoke the provided refresh token.",
)
async def logout(
    payload: LogoutRequest,
    db: AsyncSession = Depends(get_db),
) -> LogoutResponse:
    if payload.refresh_token:
        await revoke_refresh_token(db=db, raw_refresh_token=payload.refresh_token)
    return LogoutResponse(status="ok")


@router.get(
    "/me",
    response_model=UserOut,
    summary="Get current user",
    description="Retrieve the authenticated user's profile and role.",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserOut:
    return UserOut.model_validate(current_user)


@router.get(
    "/auth/sso/start",
    summary="Begin SSO login",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def sso_start() -> None:
    raise ApiError(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        code="not_implemented",
        message="SSO authentication is not implemented yet",
    )


@router.get(
    "/auth/sso/callback",
    summary="SSO callback",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def sso_callback() -> None:
    raise ApiError(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        code="not_implemented",
        message="SSO authentication is not implemented yet",
    )
