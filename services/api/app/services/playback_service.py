"""Playback token, progress tracking, captions, and chapter services."""

import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.models.enums import LectureStatus
from app.models.playback import PlaybackProgress
from app.models.user import User
from app.schemas.playback import (
    ChapterOut,
    PlaybackProgressOut,
    PlaybackProgressUpdate,
    PlaybackTokenResponse,
)
from app.services.lecture_service import get_lecture_detail
from app.settings import get_settings


def generate_signed_media_url(
    path: str,
    user_id: uuid.UUID,
    expires_at_unix: int,
    signing_key: str,
) -> str:
    """Generate signed URL with HMAC-SHA256 over path|exp|uid."""
    message = f"{path}|{expires_at_unix}|{user_id}"
    sig = hmac.new(
        signing_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{path}?exp={expires_at_unix}&uid={user_id}&sig={sig}"


def get_candidate_media_paths(path: str) -> list[str]:
    """Return all valid candidate paths that could have been signed for this resource.

    Handles:
    1. Exact path matches
    2. Caddy strip_prefix /media discrepancies (/lectures/... vs /media/lectures/...)
    3. HLS child playlist and segment URLs inheriting the signature from master.m3u8
    """
    candidates = [path]
    if path.startswith("/media"):
        candidates.append(path[len("/media"):])
    else:
        candidates.append(f"/media{path}")

    # Check if this is an HLS sub-resource (variant playlist, init mp4, segments)
    # Norm format: /media/lectures/<lecture_id>/hls/<subpath>
    norm = path if path.startswith("/media") else f"/media{path}"
    parts = norm.split("/")
    if len(parts) >= 6 and parts[1] == "media" and parts[2] == "lectures" and parts[4] == "hls":
        lecture_id = parts[3]
        candidates.append(f"/media/lectures/{lecture_id}/hls/master.m3u8")
        candidates.append(f"/lectures/{lecture_id}/hls/master.m3u8")

    return list(dict.fromkeys(candidates))


def verify_signed_media_url(
    path: str,
    user_id: str,
    exp: int,
    sig: str,
    signing_key: str,
) -> bool:
    """Validate signature and expiration for media request."""
    now_unix = int(datetime.now(UTC).timestamp())
    if exp < now_unix:
        return False

    for candidate in get_candidate_media_paths(path):
        message = f"{candidate}|{exp}|{user_id}"
        expected_sig = hmac.new(
            signing_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if hmac.compare_digest(sig, expected_sig):
            return True

    return False


async def create_playback_token(
    db: AsyncSession,
    lecture_id: uuid.UUID,
    user: User,
) -> PlaybackTokenResponse:
    """Authorize access and produce a signed master.m3u8 playback URL."""
    lecture = await get_lecture_detail(db, lecture_id, user)
    if lecture.status != LectureStatus.READY:
        raise ApiError(
            status_code=409,
            code="lecture_not_ready",
            message=f"Lecture is not ready for playback (status: {lecture.status.value})",
        )

    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.media_url_expire_minutes)
    exp_unix = int(expires_at.timestamp())

    path = f"/media/lectures/{lecture_id}/hls/master.m3u8"
    signed_url = generate_signed_media_url(
        path=path,
        user_id=user.id,
        expires_at_unix=exp_unix,
        signing_key=settings.media_signing_key,
    )

    return PlaybackTokenResponse(
        manifest_url=signed_url,
        expires_at=expires_at,
    )


async def get_playback_progress(
    db: AsyncSession,
    lecture_id: uuid.UUID,
    user: User,
) -> PlaybackProgressOut:
    """Retrieve saved resume position for a user on a lecture."""
    await get_lecture_detail(db, lecture_id, user)

    progress = await db.get(PlaybackProgress, (user.id, lecture_id))
    if progress is None:
        return PlaybackProgressOut(position_ms=0, completed=False)

    return PlaybackProgressOut(
        position_ms=progress.position_ms,
        completed=progress.completed,
    )


async def update_playback_progress(
    db: AsyncSession,
    lecture_id: uuid.UUID,
    user: User,
    data: PlaybackProgressUpdate,
) -> PlaybackProgressOut:
    """Save or update student playback position and completion status."""
    await get_lecture_detail(db, lecture_id, user)

    progress = await db.get(PlaybackProgress, (user.id, lecture_id))
    if progress is None:
        progress = PlaybackProgress(
            user_id=user.id,
            lecture_id=lecture_id,
            position_ms=data.position_ms,
            completed=data.completed,
        )
        db.add(progress)
    else:
        progress.position_ms = data.position_ms
        progress.completed = data.completed
        progress.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(progress)

    return PlaybackProgressOut(
        position_ms=progress.position_ms,
        completed=progress.completed,
    )


async def get_lecture_captions_vtt(
    db: AsyncSession,
    lecture_id: uuid.UUID,
    user: User,
    _lang: str | None = None,
) -> str:
    """Produce WebVTT captions string for lecture."""
    lecture = await get_lecture_detail(db, lecture_id, user)
    title = lecture.title

    return (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:04.500\n"
        f"Welcome to this lecture on {title}.\n\n"
        "00:00:05.000 --> 00:00:10.000\n"
        "In this session we will cover core concepts and examples.\n\n"
        "00:00:10.500 --> 00:00:16.000\n"
        "You can ask the AI tutor questions about any timestamp at any time.\n"
    )


async def get_lecture_chapters(
    db: AsyncSession,
    lecture_id: uuid.UUID,
    user: User,
) -> list[ChapterOut]:
    """Retrieve chapter list for lecture."""
    lecture = await get_lecture_detail(db, lecture_id, user)
    dur = lecture.duration_ms or 120000

    return [
        ChapterOut(
            start_ms=0,
            title="Introduction & Overview",
            summary="Session introduction and lecture goals.",
        ),
        ChapterOut(
            start_ms=int(dur * 0.25),
            title="Key Foundations",
            summary="Theoretical basis and definitions.",
        ),
        ChapterOut(
            start_ms=int(dur * 0.55),
            title="Detailed Walkthrough",
            summary="Step-by-step example problem solving.",
        ),
        ChapterOut(
            start_ms=int(dur * 0.85),
            title="Summary & Questions",
            summary="Recap of main takeaways.",
        ),
    ]
