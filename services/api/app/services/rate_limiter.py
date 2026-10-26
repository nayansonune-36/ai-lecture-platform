"""Rate limiting service using Redis with in-memory fallback."""

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import cast

import redis.asyncio as aioredis

from app.settings import get_settings

logger = logging.getLogger(__name__)

# Fallback in-memory store: key -> list of failure timestamps
_memory_store: dict[str, list[datetime]] = {}
WINDOW_SECONDS = 900  # 15 minutes

MAX_FAILED_ATTEMPTS = 5

_redis_available: bool | None = None
_redis_last_check: float = 0.0


async def _get_redis_client() -> aioredis.Redis | None:
    global _redis_available, _redis_last_check
    now = time.monotonic()
    if _redis_available is False and (now - _redis_last_check) < 10.0:
        return None

    settings = get_settings()
    try:
        client = cast(
            aioredis.Redis,
            aioredis.from_url(  # type: ignore[no-untyped-call]
                settings.redis_url,
                socket_connect_timeout=0.1,
                socket_timeout=0.1,
            ),
        )
        await client.ping()
        _redis_available = True
        return client
    except Exception:
        _redis_available = False
        _redis_last_check = now
        return None


def _cleanup_memory_store(now: datetime) -> None:
    cutoff = now - timedelta(seconds=WINDOW_SECONDS)
    keys_to_delete = []
    for key, timestamps in _memory_store.items():
        _memory_store[key] = [t for t in timestamps if t > cutoff]
        if not _memory_store[key]:
            keys_to_delete.append(key)
    for key in keys_to_delete:
        _memory_store.pop(key, None)


async def is_login_rate_limited(email: str, client_ip: str) -> bool:
    """Check if either the account or the client IP has exceeded failed login attempts."""
    account_key = f"rl:login:acc:{email.lower().strip()}"
    ip_key = f"rl:login:ip:{client_ip.strip()}"

    redis_client = await _get_redis_client()
    if redis_client is not None:
        try:
            acc_count = await redis_client.get(account_key)
            ip_count = await redis_client.get(ip_key)
            await redis_client.aclose()

            if acc_count and int(acc_count) >= MAX_FAILED_ATTEMPTS:
                return True
            if ip_count and int(ip_count) >= MAX_FAILED_ATTEMPTS:
                return True
            return False
        except Exception as exc:
            logger.warning("Redis rate limit check failed: %s, falling back to memory", exc)

    # In-memory fallback
    now = datetime.now(UTC)
    _cleanup_memory_store(now)

    cutoff = now - timedelta(seconds=WINDOW_SECONDS)
    acc_recent = [t for t in _memory_store.get(account_key, []) if t > cutoff]
    ip_recent = [t for t in _memory_store.get(ip_key, []) if t > cutoff]

    return len(acc_recent) >= MAX_FAILED_ATTEMPTS or len(ip_recent) >= MAX_FAILED_ATTEMPTS


async def record_failed_login(email: str, client_ip: str) -> None:
    """Record a failed login attempt for account and IP."""
    account_key = f"rl:login:acc:{email.lower().strip()}"
    ip_key = f"rl:login:ip:{client_ip.strip()}"

    redis_client = await _get_redis_client()
    if redis_client is not None:
        try:
            pipe = redis_client.pipeline()
            pipe.incr(account_key)
            pipe.expire(account_key, WINDOW_SECONDS)
            pipe.incr(ip_key)
            pipe.expire(ip_key, WINDOW_SECONDS)
            await pipe.execute()
            await redis_client.aclose()
            return
        except Exception as exc:
            logger.warning("Redis record failed login error: %s, falling back to memory", exc)

    # In-memory fallback
    now = datetime.now(UTC)
    _cleanup_memory_store(now)

    _memory_store.setdefault(account_key, []).append(now)
    _memory_store.setdefault(ip_key, []).append(now)


async def reset_failed_login(email: str, _client_ip: str) -> None:
    """Reset failed login count for account upon successful login."""
    account_key = f"rl:login:acc:{email.lower().strip()}"
    redis_client = await _get_redis_client()
    if redis_client is not None:
        try:
            await redis_client.delete(account_key)
            await redis_client.aclose()
        except Exception:
            pass

    _memory_store.pop(account_key, None)


def clear_memory_store() -> None:
    """Clear memory store (useful for unit tests)."""
    _memory_store.clear()


async def clear_rate_limits() -> None:
    """Clear both Redis and in-memory rate limit records (useful for test isolation)."""
    _memory_store.clear()
    redis_client = await _get_redis_client()
    if redis_client is not None:
        try:
            keys = await redis_client.keys("rl:login:*")
            if keys:
                await redis_client.delete(*keys)
            await redis_client.aclose()
        except Exception:
            pass
