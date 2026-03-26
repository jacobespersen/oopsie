"""Tests for request body size limit middleware."""

import pytest


@pytest.mark.asyncio
async def test_request_under_limit_succeeds(api_client, factory):
    """Normal-sized requests pass through."""
    from oopsie.utils.encryption import hash_api_key

    from tests.factories import OrganizationFactory, ProjectFactory

    org = await factory(OrganizationFactory)
    await factory(
        ProjectFactory, organization_id=org.id, api_key_hash=hash_api_key("key")
    )
    response = await api_client.post(
        "/api/v1/errors",
        headers={"Authorization": "Bearer key"},
        json={"error_class": "E", "message": "m"},
    )
    assert response.status_code == 202


@pytest.mark.asyncio
async def test_request_over_limit_returns_413(api_client):
    """Request body exceeding 1MB is rejected with 413."""
    # Create a payload slightly over 1MB
    huge_trace = "x" * (1024 * 1024 + 1)
    response = await api_client.post(
        "/api/v1/errors",
        headers={"Authorization": "Bearer key", "Content-Type": "application/json"},
        content=f'{{"error_class":"E","message":"m","stack_trace":"{huge_trace}"}}',
    )
    assert response.status_code == 413
