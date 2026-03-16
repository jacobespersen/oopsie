"""Redis-backed session management.

Stores user sessions as Redis hashes: session:{token} → {user_id, org_slug}.
Separate from the arq pool in queue.py — this uses plain redis.asyncio.

Known limitation: org_slug is set at login and never refreshed. If an org
slug changes, sessions serve stale URLs until they expire (up to 7 days).
"""

import secrets
from uuid import UUID

import redis.asyncio as aioredis
import redis.exceptions

from oopsie.config import get_settings
from oopsie.logging import logger

SESSION_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days

_redis_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Get or create the Redis client (lazy singleton)."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(settings.redis_url)
    return _redis_client


async def close_redis() -> None:
    """Close the Redis client (call on app shutdown)."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


async def create_session(user_id: UUID, org_slug: str | None = None) -> str:
    """Create a new session for the given user, returning the session token.

    Optionally stores org_slug so it can be retrieved without a DB query.
    Uses a Redis pipeline so HSET + EXPIRE are atomic — if the process
    crashes between them, we don't leave an immortal session key.
    """
    token = secrets.token_urlsafe(32)
    r = await get_redis()
    key = f"session:{token}"
    mapping: dict[str, str] = {"user_id": str(user_id)}
    if org_slug is not None:
        mapping["org_slug"] = org_slug
    async with r.pipeline(transaction=True) as pipe:
        pipe.hset(key, mapping=mapping)
        pipe.expire(key, SESSION_TTL_SECONDS)
        await pipe.execute()
    logger.info("session_created", user_id=str(user_id))
    return token


async def _handle_wrongtype_error(
    r: aioredis.Redis, key: str, error: redis.exceptions.ResponseError
) -> None:
    """Handle WRONGTYPE errors from pre-hash-migration string keys.

    Re-raises the error if it's not a WRONGTYPE error (e.g. OOM, read-only).
    """
    if "WRONGTYPE" not in str(error):
        raise
    logger.warning("session_key_evicted", key=key, reason="pre_hash_migration")
    try:
        await r.delete(key)
    except redis.exceptions.RedisError:
        logger.error("session_key_eviction_failed", key=key, exc_info=True)


async def get_session_user_id(token: str) -> UUID | None:
    """Look up the user ID for a session token. Returns None if missing/expired."""
    r = await get_redis()
    key = f"session:{token}"
    try:
        value: bytes | None = await r.hget(key, "user_id")  # type: ignore[misc]
    except redis.exceptions.ResponseError as e:
        await _handle_wrongtype_error(r, key, e)
        return None
    except redis.exceptions.RedisError:
        logger.error("session_user_id_redis_error", key=key, exc_info=True)
        return None
    if value is None:
        return None
    # redis returns bytes by default
    return UUID(value if isinstance(value, str) else value.decode())


async def get_session_org_slug(token: str) -> str | None:
    """Look up the org_slug for a session token. Returns None if missing/expired."""
    r = await get_redis()
    key = f"session:{token}"
    try:
        value: bytes | None = await r.hget(key, "org_slug")  # type: ignore[misc]
    except redis.exceptions.ResponseError as e:
        await _handle_wrongtype_error(r, key, e)
        return None
    except redis.exceptions.RedisError:
        logger.error("session_org_slug_redis_error", key=key, exc_info=True)
        return None
    if value is None:
        return None
    return value if isinstance(value, str) else value.decode()


async def extend_session(token: str) -> None:
    """Reset the TTL on an existing session (sliding window)."""
    r = await get_redis()
    await r.expire(f"session:{token}", SESSION_TTL_SECONDS)


async def delete_session(token: str) -> None:
    """Delete a session (instant logout)."""
    r = await get_redis()
    await r.delete(f"session:{token}")
    logger.info("session_deleted")
