"""Authentication integration tests."""

from datetime import timedelta
from typing import Any

import pytest
from fastapi import Depends
from httpx import AsyncClient

from app.core.security import create_access_token
from app.deps import require_role
from app.main import app
from app.models.enums import UserRole
from app.models.user import User

_require_prof = require_role(UserRole.PROFESSOR)


# Protected test endpoint to verify require_role
@app.get("/api/v1/test-prof-only")
async def _prof_only_endpoint(
    _user: User = Depends(_require_prof),
) -> dict[str, str]:
    return {"message": "professor access granted"}


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, seed_test_users: dict[str, Any]) -> None:
    """Successful login returns access and refresh tokens with user payload."""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "student@campus.local",
            "password": seed_test_users["student_password"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 900
    assert data["user"]["email"] == "student@campus.local"
    assert data["user"]["role"] == "student"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient) -> None:
    """Login with wrong password returns 401 invalid_credentials."""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "student@campus.local",
            "password": "WrongPassword123!",
        },
    )
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_login_inactive_user(client: AsyncClient, seed_test_users: dict[str, Any]) -> None:
    """Login for inactive user returns 403 user_inactive."""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "inactive@campus.local",
            "password": seed_test_users["inactive_password"],
        },
    )
    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "user_inactive"


@pytest.mark.asyncio
async def test_login_rate_limiting(client: AsyncClient) -> None:
    """Exceeding 5 failed login attempts triggers 429 rate_limit_exceeded."""
    for _ in range(5):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "student@campus.local", "password": "BadPassword!"},
        )
        assert resp.status_code == 401

    # 6th attempt should be blocked by rate limiter
    resp_blocked = await client.post(
        "/api/v1/auth/login",
        json={"email": "student@campus.local", "password": "BadPassword!"},
    )
    assert resp_blocked.status_code == 429
    error = resp_blocked.json()["error"]
    assert error["code"] == "rate_limit_exceeded"


@pytest.mark.asyncio
async def test_get_me_success(client: AsyncClient, seed_test_users: dict[str, Any]) -> None:
    """GET /me with valid access token returns the current user profile."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "student@campus.local",
            "password": seed_test_users["student_password"],
        },
    )
    token = login_resp.json()["access_token"]

    me_resp = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    data = me_resp.json()
    assert data["email"] == "student@campus.local"
    assert data["role"] == "student"


@pytest.mark.asyncio
async def test_get_me_expired_token(client: AsyncClient, seed_test_users: dict[str, Any]) -> None:
    """GET /me with expired token returns 401 token_expired."""
    student = seed_test_users["student"]
    expired_token = create_access_token(
        student.id,
        student.role.value,
        expires_delta=timedelta(seconds=-1),
    )

    response = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "token_expired"


@pytest.mark.asyncio
async def test_get_me_inactive_user(client: AsyncClient, seed_test_users: dict[str, Any]) -> None:
    """GET /me for inactive user returns 403 user_inactive."""
    inactive = seed_test_users["inactive"]
    token = create_access_token(inactive.id, inactive.role.value)

    response = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "user_inactive"


@pytest.mark.asyncio
async def test_refresh_token_rotation(client: AsyncClient, seed_test_users: dict[str, Any]) -> None:
    """Refresh token exchange rotates tokens; previous refresh token is invalidated."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "student@campus.local",
            "password": seed_test_users["student_password"],
        },
    )
    original_refresh = login_resp.json()["refresh_token"]

    # First rotation: original refresh token -> new tokens
    refresh_resp1 = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": original_refresh},
    )
    assert refresh_resp1.status_code == 200
    data1 = refresh_resp1.json()
    new_refresh_1 = data1["refresh_token"]
    assert new_refresh_1 != original_refresh

    # Re-using the old refresh token must fail
    replay_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": original_refresh},
    )
    assert replay_resp.status_code == 401
    assert replay_resp.json()["error"]["code"] == "invalid_refresh_token"

    # Second rotation using new_refresh_1 must succeed
    refresh_resp2 = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_refresh_1},
    )
    assert refresh_resp2.status_code == 200
    assert refresh_resp2.json()["refresh_token"] != new_refresh_1


@pytest.mark.asyncio
async def test_logout_revokes_token(client: AsyncClient, seed_test_users: dict[str, Any]) -> None:
    """Logout revokes the refresh token so subsequent refresh attempts fail."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "student@campus.local",
            "password": seed_test_users["student_password"],
        },
    )
    refresh_token = login_resp.json()["refresh_token"]

    # Logout
    logout_resp = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout_resp.status_code == 200
    assert logout_resp.json() == {"status": "ok"}

    # Attempt to refresh with logged-out token
    failed_refresh = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert failed_refresh.status_code == 401
    assert failed_refresh.json()["error"]["code"] == "invalid_refresh_token"


@pytest.mark.asyncio
async def test_require_role_enforcement(
    client: AsyncClient,
    seed_test_users: dict[str, Any],
) -> None:
    """require_role rejects users without the required role with 403."""
    # Login as student
    student_login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "student@campus.local",
            "password": seed_test_users["student_password"],
        },
    )
    student_token = student_login.json()["access_token"]

    # Student accesses professor-only endpoint -> 403
    forbidden_resp = await client.get(
        "/api/v1/test-prof-only",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert forbidden_resp.status_code == 403
    assert forbidden_resp.json()["error"]["code"] == "insufficient_permissions"

    # Login as professor
    prof_login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "prof@campus.local",
            "password": seed_test_users["professor_password"],
        },
    )
    prof_token = prof_login.json()["access_token"]

    # Professor accesses professor-only endpoint -> 200
    allowed_resp = await client.get(
        "/api/v1/test-prof-only",
        headers={"Authorization": f"Bearer {prof_token}"},
    )
    assert allowed_resp.status_code == 200


@pytest.mark.asyncio
async def test_sso_stub_endpoints(client: AsyncClient) -> None:
    """SSO start and callback endpoints return 501 Not Implemented."""
    start_resp = await client.get("/api/v1/auth/sso/start")
    assert start_resp.status_code == 501
    assert start_resp.json()["error"]["code"] == "not_implemented"

    cb_resp = await client.get("/api/v1/auth/sso/callback")
    assert cb_resp.status_code == 501
    assert cb_resp.json()["error"]["code"] == "not_implemented"
