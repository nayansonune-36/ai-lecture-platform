"""Media delivery router with signed-URL authorization and Range support."""

from fastapi import APIRouter, Query, status
from fastapi.responses import FileResponse, Response

from app.services.playback_service import verify_signed_media_url
from app.settings import get_settings

router = APIRouter(tags=["media"])


@router.get(
    "/media/{file_path:path}",
    summary="Protected media delivery",
    description="Serves media files with signed token verification and HTTP Range support.",
)
async def serve_media_file(
    file_path: str,
    exp: int = Query(...),
    uid: str = Query(...),
    sig: str = Query(...),
) -> Response:
    settings = get_settings()

    # Verify signature and expiration
    requested_path = f"/media/{file_path}"
    is_valid = verify_signed_media_url(
        path=requested_path,
        user_id=uid,
        exp=exp,
        sig=sig,
        signing_key=settings.media_signing_key,
    )
    if not is_valid:
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    storage_root = settings.resolved_storage_root
    target_file = (storage_root / file_path).resolve()

    # Prevent directory traversal
    try:
        target_file.relative_to(storage_root.resolve())
    except ValueError:
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    if not target_file.is_file():
        return Response(status_code=status.HTTP_404_NOT_FOUND)

    # FileResponse natively handles HTTP Range headers (206 Partial Content)
    return FileResponse(
        path=str(target_file),
        filename=target_file.name,
    )
