"""Job queue helper for pushing background tasks to Redis/ARQ."""

import logging
from typing import Any

from arq.connections import RedisSettings, create_pool

from app.settings import get_settings

logger = logging.getLogger(__name__)


async def enqueue_background_job(function_name: str, *args: Any, **kwargs: Any) -> str | None:
    """Enqueue a job to the Redis ARQ queue if reachable."""
    settings = get_settings()
    try:
        redis_settings = RedisSettings.from_dsn(settings.redis_url)
        pool = await create_pool(redis_settings)
        job = await pool.enqueue_job(function_name, *args, **kwargs)
        await pool.aclose()
        return str(job.job_id) if job else None
    except Exception as exc:
        logger.warning("Could not enqueue ARQ job '%s' to Redis: %s", function_name, exc)
        return None
