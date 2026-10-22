"""Health and readiness check service."""

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

import redis.asyncio as aioredis

from app.db import check_db_connection

logger = logging.getLogger(__name__)


@dataclass
class ReadinessResult:
    """Readiness status of system dependencies."""

    postgres: bool
    redis: bool
    storage: bool

    @property
    def is_ready(self) -> bool:
        """Return True if all dependencies are healthy."""
        return self.postgres and self.redis and self.storage


def check_storage_writable(storage_root: Path) -> bool:
    """Verify that storage root directory exists and is writable."""
    try:
        if not storage_root.exists() or not storage_root.is_dir():
            return False
        probe_file = storage_root / f".probe_{uuid.uuid4().hex}"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink(missing_ok=True)
        return True
    except Exception as exc:
        logger.warning("Storage write check failed at %s: %s", storage_root, exc)
        return False


async def check_redis_reachable(redis_url: str) -> bool:
    """Verify connectivity to Redis."""
    try:
        client = aioredis.from_url(  # type: ignore[no-untyped-call]
            redis_url, socket_connect_timeout=2.0
        )
        await client.ping()
        await client.aclose()
        return True
    except Exception as exc:
        logger.warning("Redis connectivity check failed for %s: %s", redis_url, exc)
        return False


async def check_readiness(storage_root: Path, redis_url: str) -> ReadinessResult:
    """Run all readiness checks."""
    postgres_ready = await check_db_connection()
    redis_ready = await check_redis_reachable(redis_url)
    storage_ready = check_storage_writable(storage_root)

    return ReadinessResult(
        postgres=postgres_ready,
        redis=redis_ready,
        storage=storage_ready,
    )
