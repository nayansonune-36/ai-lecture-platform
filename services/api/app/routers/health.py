"""Health and readiness router."""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services.health import check_readiness
from app.settings import get_settings

router = APIRouter(tags=["health"])


class HealthzResponse(BaseModel):
    """Response model for healthz check."""

    status: str = "ok"


class ReadyzResponse(BaseModel):
    """Response model for readyz check."""

    status: str
    postgres: bool
    redis: bool
    storage: bool


@router.get(
    "/healthz",
    response_model=HealthzResponse,
    summary="Liveness check",
    description="Returns 200 OK when the application process is running.",
)
async def get_healthz() -> HealthzResponse:
    """Return basic liveness status."""
    return HealthzResponse(status="ok")


@router.get(
    "/readyz",
    response_model=ReadyzResponse,
    responses={
        status.HTTP_200_OK: {"model": ReadyzResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadyzResponse},
    },
    summary="Readiness check",
    description="Checks reachability of PostgreSQL, Redis, and writable storage root.",
)
async def get_readyz() -> JSONResponse:
    """Check dependencies and return readiness status."""
    settings = get_settings()
    result = await check_readiness(
        storage_root=settings.storage_root,
        redis_url=settings.redis_url,
    )

    response_data = ReadyzResponse(
        status="ready" if result.is_ready else "not_ready",
        postgres=result.postgres,
        redis=result.redis,
        storage=result.storage,
    )

    status_code = status.HTTP_200_OK if result.is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=status_code, content=response_data.model_dump())
