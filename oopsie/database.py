"""Database setup: async engine and session for FastAPI."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import lru_cache
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from oopsie.config import get_settings
from oopsie.logging import logger


def _adapt_url_for_asyncpg(url: str) -> str:
    """Convert psycopg2-style connection params to asyncpg-compatible ones.

    asyncpg uses 'ssl' instead of 'sslmode' and doesn't support 'channel_binding'.
    """
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    if "sslmode" in params:
        params["ssl"] = params.pop("sslmode")
    params.pop("channel_binding", None)

    new_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=new_query))


@lru_cache
def _get_engine():
    """Create the async engine lazily (on first call, not at import time)."""
    return create_async_engine(
        _adapt_url_for_asyncpg(get_settings().database_url),
        echo=False,
        pool_use_lifo=True,
        pool_size=5,
    )


@lru_cache
def _get_session_factory():
    """Create the session factory lazily, bound to the lazy engine."""
    return async_sessionmaker(
        _get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


@asynccontextmanager
async def worker_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for DB sessions (FastAPI DI and worker jobs)."""
    async with _get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            logger.warning("db_session_rollback")
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session."""
    async with worker_session() as session:
        yield session


async def close_engine() -> None:
    """Dispose of the engine (for worker shutdown)."""
    await _get_engine().dispose()
