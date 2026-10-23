"""FastAPI application main module."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.errors import ApiError
from app.core.license import get_public_key_pem
from app.db import engine
from app.routers import auth, courses, health, lectures, media, offline, playback
from app.schemas.device import LicensePublicKeyResponse


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager handling startup and shutdown."""
    yield
    # Dispose database engine on shutdown
    await engine.dispose()


app = FastAPI(
    title="AI Lecture Platform API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


@app.exception_handler(ApiError)
async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    """Ensure all ApiError responses match docs/api.md schema."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        headers=exc.headers,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    """Format standard HTTPExceptions consistently."""
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        error_content = {
            "code": detail.get("code", "http_error"),
            "message": detail.get("message", "An error occurred"),
            "details": detail.get("details", {}),
        }
    else:
        error_content = {
            "code": "http_error",
            "message": str(detail),
            "details": {},
        }
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error_content},
        headers=exc.headers,
    )


# Mount routes under /api/v1 (standard API base path)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(courses.router, prefix="/api/v1")
app.include_router(lectures.router, prefix="/api/v1")
app.include_router(offline.router, prefix="/api/v1")
app.include_router(playback.router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1")

# Media delivery with signed token verification and Range support
app.include_router(media.router)

# Also mount health and license public key at root
app.include_router(health.router)


@app.get(
    "/license-public-key",
    response_model=LicensePublicKeyResponse,
    summary="Get license verification public key (root alias)",
    tags=["offline"],
)
async def get_license_public_key_root() -> LicensePublicKeyResponse:
    return LicensePublicKeyResponse(
        public_key=get_public_key_pem(),
        algorithm="Ed25519",
    )
