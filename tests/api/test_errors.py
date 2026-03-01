"""Integration tests for POST /api/v1/errors."""

import pytest
from oopsie.models import Error, ErrorOccurrence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_ingest_error_creates_error_and_occurrence(
    api_client,
    db_session: AsyncSession,
    project_with_api_key,
):
    """POST /api/v1/errors with valid API key returns 202."""
    response = await api_client.post(
        "/api/v1/errors",
        headers={"Authorization": "Bearer test-api-key-123"},
        json={
            "error_class": "NoMethodError",
            "message": "undefined method 'foo' for nil:NilClass",
            "stack_trace": "app/models/user.rb:42:in `display_name'",
        },
    )
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}

    result = await db_session.execute(select(Error))
    error = result.scalar_one_or_none()
    assert error is not None
    assert error.error_class == "NoMethodError"
    assert error.message == "undefined method 'foo' for nil:NilClass"
    assert error.occurrence_count == 1
    assert error.project_id == project_with_api_key.id

    result = await db_session.execute(select(ErrorOccurrence))
    occurrence = result.scalar_one_or_none()
    assert occurrence is not None
    assert occurrence.error_id == error.id


@pytest.mark.asyncio
async def test_ingest_error_duplicate_increments_count_and_adds_occurrence(
    api_client,
    db_session: AsyncSession,
    project_with_api_key,
):
    """Duplicate request increments count and adds occurrence."""
    body = {
        "error_class": "NoMethodError",
        "message": "undefined method 'foo' for nil:NilClass",
        "stack_trace": "app/models/user.rb:42",
    }
    headers = {"Authorization": "Bearer test-api-key-123"}

    r1 = await api_client.post("/api/v1/errors", headers=headers, json=body)
    assert r1.status_code == 202

    r2 = await api_client.post("/api/v1/errors", headers=headers, json=body)
    assert r2.status_code == 202

    result = await db_session.execute(
        select(Error).where(Error.project_id == project_with_api_key.id)
    )
    error = result.scalar_one()
    assert error.occurrence_count == 2

    result = await db_session.execute(
        select(ErrorOccurrence).where(ErrorOccurrence.error_id == error.id)
    )
    occurrences = result.scalars().all()
    assert len(occurrences) == 2


@pytest.mark.asyncio
async def test_ingest_error_unauthorized_without_api_key(api_client):
    """POST /api/v1/errors without Authorization returns 401."""
    response = await api_client.post(
        "/api/v1/errors",
        json={"error_class": "E", "message": "m"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ingest_error_unauthorized_invalid_api_key(
    api_client,
    project_with_api_key,
):
    """POST /api/v1/errors with wrong API key returns 401."""
    response = await api_client.post(
        "/api/v1/errors",
        headers={"Authorization": "Bearer wrong-key"},
        json={"error_class": "E", "message": "m"},
    )
    assert response.status_code == 401
