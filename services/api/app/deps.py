"""Application dependency injectors."""

import uuid
from collections.abc import Callable

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import forbidden, unauthorized
from app.core.security import decode_access_token
from app.db import get_db
from app.models.enums import UserRole
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency that extracts and validates the bearer token and returns the current user."""
    if credentials is None or not credentials.credentials:
        raise unauthorized("Authentication required", code="unauthorized")

    token = credentials.credentials
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError as err:
        raise unauthorized("Token has expired", code="token_expired") from err
    except jwt.PyJWTError as err:
        raise unauthorized("Invalid token", code="invalid_token") from err

    sub = payload.get("sub")
    if sub is None:
        raise unauthorized("Invalid token payload", code="invalid_token")

    try:
        user_uuid = uuid.UUID(sub)
    except ValueError as err:
        raise unauthorized("Invalid user identifier in token", code="invalid_token") from err

    stmt = select(User).where(User.id == user_uuid)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise unauthorized("User not found", code="user_not_found")

    if not user.is_active:
        raise forbidden("Account is inactive", code="user_inactive")

    return user


def require_role(*roles: UserRole) -> Callable[..., User]:
    """Dependency factory requiring the current user to possess one of the specified roles."""

    def role_dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise forbidden("Insufficient permissions", code="insufficient_permissions")
        return current_user

    return role_dependency
