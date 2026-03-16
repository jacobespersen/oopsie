"""Tests for main app routes (health, root redirect)."""

import pytest


@pytest.mark.asyncio
async def test_health_returns_ok(api_client):
    """GET /health returns status ok."""
    response = await api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
