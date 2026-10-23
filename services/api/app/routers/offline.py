"""Offline bundle routes."""

import uuid

from fastapi import APIRouter, Body, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas.bundle import (
    OfflineBundleRequest,
    OfflineBundleResponse,
    OfflineEstimateResponse,
)
from app.services.bundle_service import (
    get_offline_bundle_status,
    get_offline_estimate,
    request_offline_bundle,
)

router = APIRouter(tags=["offline"])


@router.get(
    "/lectures/{id}/offline-estimate",
    response_model=OfflineEstimateResponse,
    summary="Estimate offline bundle size",
    description="Returns approximate size in bytes for chosen rendition before download.",
)
async def get_bundle_estimate(
    lecture_id: uuid.UUID = Path(..., alias="id"),
    rendition: int = Query(480, description="Rendition height (720, 480, 360)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OfflineEstimateResponse:
    return await get_offline_estimate(
        db=db,
        lecture_id=lecture_id,
        rendition=rendition,
        user=current_user,
    )


@router.post(
    "/lectures/{id}/offline-bundle",
    response_model=OfflineBundleResponse,
    status_code=status.HTTP_200_OK,
    summary="Request offline bundle packaging",
    description="Queue bundle creation or immediately return signed download URL if ready.",
)
async def create_offline_bundle(
    lecture_id: uuid.UUID = Path(..., alias="id"),
    payload: OfflineBundleRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OfflineBundleResponse:
    return await request_offline_bundle(
        db=db,
        lecture_id=lecture_id,
        payload=payload,
        user=current_user,
    )


@router.get(
    "/offline-bundles/{job_id}",
    response_model=OfflineBundleResponse,
    summary="Check offline bundle status",
    description="Returns job status and signed download URL when bundle packaging is complete.",
)
async def get_bundle_status(
    job_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OfflineBundleResponse:
    return await get_offline_bundle_status(
        db=db,
        job_id=job_id,
        user=current_user,
    )
