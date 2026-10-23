"""Offline bundle, device registration, and license renewal routes."""

import uuid

from fastapi import APIRouter, Body, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.license import get_public_key_pem
from app.db import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas.bundle import (
    OfflineBundleRequest,
    OfflineBundleResponse,
    OfflineEstimateResponse,
)
from app.schemas.device import (
    DeviceCreate,
    DeviceOut,
    LicensePublicKeyResponse,
    LicenseRenewRequest,
    LicenseRenewResponse,
)
from app.services.bundle_service import (
    get_offline_bundle_status,
    get_offline_estimate,
    request_offline_bundle,
)
from app.services.device_service import (
    list_user_devices,
    register_device,
    renew_offline_licenses,
    revoke_device,
)

router = APIRouter(tags=["offline"])


# --- Devices ---


@router.post(
    "/devices",
    response_model=DeviceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new device",
    description="Register device with public key. Maximum 3 active devices per user.",
)
async def create_device(
    payload: DeviceCreate = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DeviceOut:
    return await register_device(db=db, payload=payload, user=current_user)


@router.get(
    "/devices",
    response_model=list[DeviceOut],
    summary="List registered devices",
    description="List all devices belonging to the authenticated user.",
)
async def get_devices(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DeviceOut]:
    return await list_user_devices(db=db, user=current_user)


@router.delete(
    "/devices/{id}",
    status_code=status.HTTP_200_OK,
    summary="Revoke a device",
    description="Marks device as revoked and invalidates all its offline licenses.",
)
async def delete_device(
    device_id: uuid.UUID = Path(..., alias="id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    await revoke_device(db=db, device_id=device_id, user=current_user)
    return {"status": "ok", "message": "Device revoked"}


# --- Public Key & Licenses ---


@router.get(
    "/license-public-key",
    response_model=LicensePublicKeyResponse,
    summary="Get license verification public key",
    description="Returns Ed25519 public key in PEM format used to verify offline license tokens.",
)
async def get_license_public_key() -> LicensePublicKeyResponse:
    return LicensePublicKeyResponse(
        public_key=get_public_key_pem(),
        algorithm="Ed25519",
    )


@router.post(
    "/offline-licenses/renew",
    response_model=LicenseRenewResponse,
    status_code=status.HTTP_200_OK,
    summary="Renew offline licenses for a device",
    description="Extends valid licenses and returns revoked IDs for unavailable lectures.",
)
async def renew_licenses(
    payload: LicenseRenewRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LicenseRenewResponse:
    return await renew_offline_licenses(db=db, payload=payload, user=current_user)


# --- Bundles ---


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
    description="Returns job status, metadata, signed download URL, and license token.",
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
