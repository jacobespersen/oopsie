"""arq WorkerSettings for the Oopsie worker process."""

from arq.connections import RedisSettings

from oopsie.config import get_settings
from oopsie.database import close_engine
from oopsie.queue import close_arq_pool
from oopsie.worker.fix_pipeline import run_fix_pipeline


async def on_startup(ctx: dict) -> None:
    """Worker startup hook."""


async def on_shutdown(ctx: dict) -> None:
    """Worker shutdown hook."""
    await close_arq_pool()
    await close_engine()


class WorkerSettings:
    functions = [run_fix_pipeline]
    on_startup = on_startup
    on_shutdown = on_shutdown

    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = get_settings().worker_concurrency
    job_timeout = get_settings().job_timeout_seconds
