"""Redis-backed session management.

Stores user sessions as simple key-value pairs: session:{token} → user_id.
Separate from the arq pool in queue.py — this uses plain redis.asyncio.
"""

import secrets
from uuid import UUID

import redis.asyncio as aioredis

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


async def create_session(user_id: UUID) -> str:
    """Create a new session for the given user, returning the session token."""
    token = secrets.token_urlsafe(32)
    r = await get_redis()
    await r.set(f"session:{token}", str(user_id), ex=SESSION_TTL_SECONDS)
    logger.info("session_created", user_id=str(user_id))
    return token


async def get_session_user_id(token: str) -> UUID | None:
    """Look up the user ID for a session token. Returns None if missing/expired."""
    r = await get_redis()
    value = await r.get(f"session:{token}")
    if value is None:
        return None
    # redis returns bytes by default
    return UUID(value if isinstance(value, str) else value.decode())


async def extend_session(token: str) -> None:
    """Reset the TTL on an existing session (sliding window)."""
    r = await get_redis()
    await r.expire(f"session:{token}", SESSION_TTL_SECONDS)


async def delete_session(token: str) -> None:
    """Delete a session (instant logout)."""
    r = await get_redis()
    await r.delete(f"session:{token}")
    logger.info("session_deleted")
