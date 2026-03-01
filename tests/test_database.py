"""Tests for database session dependency."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from oopsie.database import get_session


@pytest.mark.asyncio
async def test_get_session_yields_and_commits():
    """get_session yields a session, commits on success, and closes."""
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session.rollback = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None

    mock_factory = MagicMock(return_value=mock_cm)

    with patch("oopsie.database.async_session_factory", mock_factory):
        gen = get_session()
        async for session in gen:
            assert session is mock_session

    mock_session.commit.assert_awaited_once()
    mock_session.close.assert_awaited_once()
    mock_session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_session_rolls_back_on_exception():
    """get_session rolls back and re-raises when commit fails."""
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock(side_effect=RuntimeError("commit failed"))
    mock_session.close = AsyncMock()
    mock_session.rollback = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None

    mock_factory = MagicMock(return_value=mock_cm)

    with patch("oopsie.database.async_session_factory", mock_factory):
        gen = get_session()
        with pytest.raises(RuntimeError, match="commit failed"):
            async for session in gen:
                pass

    mock_session.rollback.assert_awaited_once()
    mock_session.close.assert_awaited_once()
