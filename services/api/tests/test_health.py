"""Tests for health and readiness endpoints."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.health import check_storage_writable

client = TestClient(app)


def test_healthz_root() -> None:
    """GET /healthz returns 200 OK."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_v1() -> None:
    """GET /api/v1/healthz returns 200 OK."""
    response = client.get("/api/v1/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_all_healthy() -> None:
    """GET /api/v1/readyz returns 200 when all dependencies are healthy."""
    with (
        patch("app.services.health.check_db_connection", new_callable=AsyncMock) as mock_db,
        patch("app.services.health.check_redis_reachable", new_callable=AsyncMock) as mock_redis,
        patch("app.services.health.check_storage_writable", return_value=True) as mock_storage,
    ):
        mock_db.return_value = True
        mock_redis.return_value = True

        response = client.get("/api/v1/readyz")
        assert response.status_code == 200
        data = response.json()
        assert data == {
            "status": "ready",
            "postgres": True,
            "redis": True,
            "storage": True,
        }
        mock_db.assert_awaited_once()
        mock_redis.assert_awaited_once()
        mock_storage.assert_called_once()


def test_readyz_dependency_unhealthy() -> None:
    """GET /api/v1/readyz returns 503 when any dependency is down."""
    with (
        patch("app.services.health.check_db_connection", new_callable=AsyncMock) as mock_db,
        patch("app.services.health.check_redis_reachable", new_callable=AsyncMock) as mock_redis,
        patch("app.services.health.check_storage_writable", return_value=True),
    ):
        mock_db.return_value = False
        mock_redis.return_value = True

        response = client.get("/api/v1/readyz")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["postgres"] is False
        assert data["redis"] is True
        assert data["storage"] is True


def test_check_storage_writable(tmp_path: Path) -> None:
    """Verify storage write check creates and cleans up probe file."""
    assert check_storage_writable(tmp_path) is True
    non_existent = tmp_path / "not_a_dir"
    assert check_storage_writable(non_existent) is False
