"""Playback, progress, WebVTT captions, and chapters router."""

import uuid

from fastapi import APIRouter, Body, Depends, Path, Query, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas.playback import (
    ChapterOut,
    PlaybackProgressOut,
    PlaybackProgressUpdate,
    PlaybackTokenResponse,
)
from app.services.playback_service import (
    create_playback_token,
    get_lecture_captions_vtt,
    get_lecture_chapters,
    get_playback_progress,
    update_playback_progress,
    verify_signed_media_url,
)
from app.settings import get_settings

router = APIRouter(tags=["playback"])


@router.post(
    "/lectures/{id}/playback-token",
    response_model=PlaybackTokenResponse,
    summary="Get signed playback token",
    description="Returns signed HLS master playlist URL and expiration timestamp.",
)
async def get_playback_token(
    lecture_id: uuid.UUID = Path(..., alias="id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PlaybackTokenResponse:
    return await create_playback_token(db=db, lecture_id=lecture_id, user=current_user)


@router.get(
    "/lectures/{id}/captions.vtt",
    response_class=PlainTextResponse,
    summary="Get lecture captions in WebVTT format",
    description="Returns WebVTT caption cues for the lecture player.",
)
async def get_captions(
    lecture_id: uuid.UUID = Path(..., alias="id"),
    lang: str | None = Query(None, description="Language code (e.g. en, hi)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    vtt_content = await get_lecture_captions_vtt(
        db=db,
        lecture_id=lecture_id,
        user=current_user,
        _lang=lang,
    )
    return PlainTextResponse(content=vtt_content, media_type="text/vtt")


@router.get(
    "/lectures/{id}/chapters",
    response_model=list[ChapterOut],
    summary="Get lecture chapters",
    description="Returns chapter markers with start timestamps in milliseconds.",
)
async def get_chapters(
    lecture_id: uuid.UUID = Path(..., alias="id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChapterOut]:
    return await get_lecture_chapters(db=db, lecture_id=lecture_id, user=current_user)


@router.get(
    "/lectures/{id}/progress",
    response_model=PlaybackProgressOut,
    summary="Get playback resume progress",
    description="Retrieve saved playback position in milliseconds.",
)
async def get_progress(
    lecture_id: uuid.UUID = Path(..., alias="id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PlaybackProgressOut:
    return await get_playback_progress(db=db, lecture_id=lecture_id, user=current_user)


@router.put(
    "/lectures/{id}/progress",
    response_model=PlaybackProgressOut,
    summary="Save playback progress",
    description="Update current resume position in milliseconds every 10s or on pause/leave.",
)
async def save_progress(
    lecture_id: uuid.UUID = Path(..., alias="id"),
    payload: PlaybackProgressUpdate = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PlaybackProgressOut:
    return await update_playback_progress(
        db=db,
        lecture_id=lecture_id,
        user=current_user,
        data=payload,
    )


@router.get(
    "/internal/auth/video",
    summary="Internal video verification for Caddy forward_auth",
    description="Validates signature and expiry for incoming /media/* requests.",
)
async def internal_verify_video(
    path: str = Query(...),
    uid: str = Query(...),
    exp: int = Query(...),
    sig: str = Query(...),
) -> Response:
    settings = get_settings()
    is_valid = verify_signed_media_url(
        path=path,
        user_id=uid,
        exp=exp,
        sig=sig,
        signing_key=settings.media_signing_key,
    )
    if not is_valid:
        return Response(status_code=status.HTTP_403_FORBIDDEN)
    return Response(status_code=status.HTTP_200_OK)
