"""Tests for oopsie.queue."""

from unittest.mock import AsyncMock, patch

import pytest
from oopsie.queue import close_arq_pool, enqueue_fix_job, get_arq_pool


@pytest.fixture(autouse=True)
def _reset_pool():
    """Reset the module-level pool before each test."""
    import oopsie.queue as mod

    mod._arq_pool = None
    yield
    mod._arq_pool = None


@pytest.mark.asyncio
async def test_get_arq_pool_creates_pool():
    mock_pool = AsyncMock()
    with patch("oopsie.queue.create_pool", return_value=mock_pool) as mock_create:
        pool = await get_arq_pool()
        assert pool is mock_pool
        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_get_arq_pool_returns_same_pool():
    mock_pool = AsyncMock()
    with patch("oopsie.queue.create_pool", return_value=mock_pool) as mock_create:
        p1 = await get_arq_pool()
        p2 = await get_arq_pool()
        assert p1 is p2
        assert mock_create.call_count == 1


@pytest.mark.asyncio
async def test_close_arq_pool():
    mock_pool = AsyncMock()
    with patch("oopsie.queue.create_pool", return_value=mock_pool):
        await get_arq_pool()
        await close_arq_pool()
        mock_pool.close.assert_called_once()

    import oopsie.queue as mod

    assert mod._arq_pool is None


@pytest.mark.asyncio
async def test_close_arq_pool_noop_when_none():
    # Should not raise
    await close_arq_pool()


@pytest.mark.asyncio
async def test_enqueue_fix_job():
    mock_pool = AsyncMock()
    with patch("oopsie.queue.create_pool", return_value=mock_pool):
        await enqueue_fix_job("err-123", "proj-456")
        mock_pool.enqueue_job.assert_called_once_with(
            "run_fix_pipeline",
            "err-123",
            "proj-456",
        )
