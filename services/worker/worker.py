"""ARQ Worker configuration and job definitions."""

import logging
from typing import Any

from arq.connections import RedisSettings

from bundle_job import bundle_lecture_job
from settings import get_settings
from transcode_job import transcode_lecture_job

logger = logging.getLogger(__name__)


async def startup(_ctx: dict[str, Any]) -> None:
    """Worker startup hook."""
    settings = get_settings()
    logger.info("ARQ Worker starting up. Storage root: %s", settings.resolved_storage_root)
    logger.info("FFmpeg binary: %s", settings.get_ffmpeg_binary())
    logger.info("FFprobe binary: %s", settings.get_ffprobe_binary())


async def shutdown(_ctx: dict[str, Any]) -> None:
    """Worker shutdown hook."""
    logger.info("ARQ Worker shutting down.")


async def transcode(
    ctx: dict[str, Any],
    lecture_id: str,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Execute transcode job within ARQ worker context with up to 3 retries."""
    job_try = ctx.get("job_try", 1)
    logger.info(
        "ARQ executing 'transcode' for lecture %s (job_id=%s, try=%d)",
        lecture_id,
        job_id,
        job_try,
    )
    return await transcode_lecture_job(lecture_id=lecture_id, job_id=job_id, attempt=job_try)


async def bundle(
    ctx: dict[str, Any],
    lecture_id: str,
    rendition: int,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Execute offline bundle creation job within ARQ worker context."""
    job_try = ctx.get("job_try", 1)
    logger.info(
        "ARQ executing 'bundle' for lecture %s (rendition=%dp, job_id=%s, try=%d)",
        lecture_id,
        rendition,
        job_id,
        job_try,
    )
    return await bundle_lecture_job(
        lecture_id=lecture_id,
        rendition=rendition,
        job_id=job_id,
        attempt=job_try,
    )


class WorkerSettings:
    """ARQ worker settings."""

    functions: list[Any] = [transcode, bundle]
    on_startup = startup
    on_shutdown = shutdown
    max_tries: int = 3
    retry_jobs: bool = True
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
