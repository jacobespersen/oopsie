"""Redis/arq queue infrastructure."""

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from oopsie.config import get_settings
from oopsie.logging import logger

_arq_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis:
    """Get or create the arq Redis connection pool (lazy singleton)."""
    global _arq_pool
    if _arq_pool is None:
        settings = get_settings()
        _arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _arq_pool


async def close_arq_pool() -> None:
    """Close the arq pool (call on app/worker shutdown)."""
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.close()
        _arq_pool = None


async def enqueue_fix_job(error_id: str, project_id: str) -> None:
    """Enqueue a fix pipeline job. Deduplicates by error_id."""
    pool = await get_arq_pool()
    await pool.enqueue_job(
        "run_fix_pipeline",
        error_id,
        project_id,
    )
    logger.info("fix_job_enqueued", error_id=error_id, project_id=project_id)
