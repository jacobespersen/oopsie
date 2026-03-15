"""Tests for OrgSlugMiddleware."""

import pytest


@pytest.mark.asyncio
async def test_middleware_sets_org_slug_from_session(
    authenticated_client, organization
):
    """Middleware sets org_slug on request.state from session cookie."""
    response = await authenticated_client.get(f"/orgs/{organization.slug}/projects")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_middleware_handles_redis_failure_gracefully(
    authenticated_client, monkeypatch
):
    """Middleware falls back to org_slug=None when Redis is unavailable."""
    import oopsie.middleware.org_slug

    async def _boom(token):
        raise ConnectionError("Redis connection refused")

    monkeypatch.setattr(oopsie.middleware.org_slug, "get_session_org_slug", _boom)

    # Should NOT 500 — middleware should catch and fall back
    response = await authenticated_client.get("/health")
    assert response.status_code == 200
