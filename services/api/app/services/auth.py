"""Authentication and token management business logic."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import forbidden, rate_limited, unauthorized
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_token,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.rate_limiter import (
    is_login_rate_limited,
    record_failed_login,
    reset_failed_login,
)
from app.settings import get_settings


def _ensure_utc(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware in UTC (handles SQLite naive timestamps)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
    client_ip: str,
) -> tuple[User, str, str]:
    """Authenticate a user with email and password and issue tokens."""
    settings = get_settings()
    clean_email = email.lower().strip()

    # 1. Check rate limit
    if await is_login_rate_limited(clean_email, client_ip):
        raise rate_limited()

    # 2. Query user
    stmt = select(User).where(func.lower(User.email) == clean_email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if (
        user is None
        or user.password_hash is None
        or not verify_password(password, user.password_hash)
    ):
        await record_failed_login(clean_email, client_ip)
        raise unauthorized("Invalid email or password", code="invalid_credentials")

    # 3. Check active status
    if not user.is_active:
        raise forbidden("Account is inactive", code="user_inactive")

    # 4. Successful login: reset failed login count
    await reset_failed_login(clean_email, client_ip)

    # 5. Issue access token
    access_token = create_access_token(user.id, user.role.value)

    # 6. Issue refresh token
    raw_refresh = generate_refresh_token()
    token_h = hash_token(raw_refresh)
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)

    refresh_entity = RefreshToken(
        user_id=user.id,
        token_hash=token_h,
        expires_at=expires_at,
    )
    db.add(refresh_entity)
    await db.commit()
    await db.refresh(user)

    return user, access_token, raw_refresh


async def rotate_refresh_token(
    db: AsyncSession,
    raw_refresh_token: str,
) -> tuple[str, str]:
    """Validate and rotate a refresh token."""
    settings = get_settings()
    token_h = hash_token(raw_refresh_token)

    stmt = select(RefreshToken).where(RefreshToken.token_hash == token_h)
    result = await db.execute(stmt)
    token_entity = result.scalar_one_or_none()

    now = datetime.now(UTC)
    if (
        token_entity is None
        or token_entity.revoked_at is not None
        or _ensure_utc(token_entity.expires_at) <= now
    ):
        raise unauthorized("Invalid or expired refresh token", code="invalid_refresh_token")

    # Fetch user
    user_stmt = select(User).where(User.id == token_entity.user_id)
    user_res = await db.execute(user_stmt)
    user = user_res.scalar_one_or_none()

    if user is None or not user.is_active:
        raise forbidden("Account is inactive", code="user_inactive")

    # Rotate: revoke old, create new
    token_entity.revoked_at = now

    new_raw_refresh = generate_refresh_token()
    new_token_h = hash_token(new_raw_refresh)
    new_expires_at = now + timedelta(days=settings.refresh_token_expire_days)

    new_token_entity = RefreshToken(
        user_id=user.id,
        token_hash=new_token_h,
        expires_at=new_expires_at,
    )
    db.add(new_token_entity)

    new_access_token = create_access_token(user.id, user.role.value)
    await db.commit()

    return new_access_token, new_raw_refresh


async def revoke_refresh_token(
    db: AsyncSession,
    raw_refresh_token: str,
) -> None:
    """Revoke a refresh token on logout."""
    token_h = hash_token(raw_refresh_token)
    stmt = select(RefreshToken).where(
        RefreshToken.token_hash == token_h,
        RefreshToken.revoked_at.is_(None),
    )
    result = await db.execute(stmt)
    token_entity = result.scalar_one_or_none()

    if token_entity is not None:
        token_entity.revoked_at = datetime.now(UTC)
        await db.commit()
