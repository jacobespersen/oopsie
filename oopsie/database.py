"""Database setup: async engine and session for FastAPI."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from oopsie.config import get_settings
from oopsie.logging import logger

engine = create_async_engine(
    get_settings().database_url,
    echo=False,
)
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@asynccontextmanager
async def worker_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for DB sessions (FastAPI DI and worker jobs)."""
    async with async_session_factory() as session:
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
    await engine.dispose()
