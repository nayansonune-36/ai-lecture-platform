"""API exception definitions and helpers."""

from typing import Any

from fastapi import HTTPException, status


class ApiError(HTTPException):
    """Base API exception that adheres to the docs/api.md error schema."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(
            status_code=status_code,
            detail={"code": code, "message": message, "details": self.details},
            headers=headers,
        )


def unauthorized(message: str = "Invalid credentials", code: str = "unauthorized") -> ApiError:
    return ApiError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code=code,
        message=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


def forbidden(message: str = "Forbidden", code: str = "forbidden") -> ApiError:
    return ApiError(
        status_code=status.HTTP_403_FORBIDDEN,
        code=code,
        message=message,
    )


def rate_limited(
    message: str = "Too many failed attempts. Try again later.",
    code: str = "rate_limit_exceeded",
) -> ApiError:
    return ApiError(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        code=code,
        message=message,
    )
