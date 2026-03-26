"""Integration tests for POST /api/v1/errors."""

import pytest
from oopsie.models import Error, ErrorOccurrence
from oopsie.utils.encryption import hash_api_key
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import OrganizationFactory, ProjectFactory

_API_KEY = "test-api-key-123"


@pytest.mark.asyncio
async def test_ingest_error_creates_error_and_occurrence(
    api_client,
    db_session: AsyncSession,
    factory,
):
    """POST /api/v1/errors with valid API key returns 202."""
    org = await factory(OrganizationFactory)
    project = await factory(
        ProjectFactory, organization_id=org.id, api_key_hash=hash_api_key(_API_KEY)
    )
    response = await api_client.post(
        "/api/v1/errors",
        headers={"Authorization": f"Bearer {_API_KEY}"},
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
    assert error.project_id == project.id

    result = await db_session.execute(select(ErrorOccurrence))
    occurrence = result.scalar_one_or_none()
    assert occurrence is not None
    assert occurrence.error_id == error.id


@pytest.mark.asyncio
async def test_ingest_error_duplicate_increments_count_and_adds_occurrence(
    api_client,
    db_session: AsyncSession,
    factory,
):
    """Duplicate request increments count and adds occurrence."""
    org = await factory(OrganizationFactory)
    project = await factory(
        ProjectFactory, organization_id=org.id, api_key_hash=hash_api_key(_API_KEY)
    )
    body = {
        "error_class": "NoMethodError",
        "message": "undefined method 'foo' for nil:NilClass",
        "stack_trace": "app/models/user.rb:42",
    }
    headers = {"Authorization": f"Bearer {_API_KEY}"}

    r1 = await api_client.post("/api/v1/errors", headers=headers, json=body)
    assert r1.status_code == 202

    r2 = await api_client.post("/api/v1/errors", headers=headers, json=body)
    assert r2.status_code == 202

    result = await db_session.execute(
        select(Error).where(Error.project_id == project.id)
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
async def test_ingest_error_unauthorized_invalid_api_key(api_client, factory):
    """POST /api/v1/errors with wrong API key returns 401."""
    org = await factory(OrganizationFactory)
    await factory(
        ProjectFactory, organization_id=org.id, api_key_hash=hash_api_key(_API_KEY)
    )
    response = await api_client.post(
        "/api/v1/errors",
        headers={"Authorization": "Bearer wrong-key"},
        json={"error_class": "E", "message": "m"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ingest_error_with_exception_chain_and_execution_context(
    api_client,
    db_session: AsyncSession,
    factory,
):
    """POST with exception_chain and execution_context stores them on occurrence."""
    org = await factory(OrganizationFactory)
    await factory(
        ProjectFactory, organization_id=org.id, api_key_hash=hash_api_key(_API_KEY)
    )
    response = await api_client.post(
        "/api/v1/errors",
        headers={"Authorization": f"Bearer {_API_KEY}"},
        json={
            "error_class": "AuthError",
            "message": "Login failed",
            "stack_trace": "app/controllers/sessions.rb:18",
            "exception_chain": [
                {
                    "type": "ActiveRecord::RecordNotFound",
                    "value": "Couldn't find User",
                    "module": "ActiveRecord",
                    "mechanism": {"type": "chained", "handled": False},
                    "stacktrace": [
                        {
                            "file": "app/models/user.rb",
                            "function": "find_or_raise",
                            "lineno": 42,
                            "in_app": True,
                        },
                    ],
                },
                {
                    "type": "AuthError",
                    "value": "Login failed",
                    "stacktrace": [
                        {
                            "file": "app/controllers/sessions.rb",
                            "function": "create",
                            "lineno": 18,
                            "in_app": True,
                        },
                    ],
                },
            ],
            "execution_context": {
                "type": "http",
                "description": "POST /api/sessions",
                "data": {"method": "POST", "url": "/api/sessions"},
            },
        },
    )
    assert response.status_code == 202

    result = await db_session.execute(select(ErrorOccurrence))
    occ = result.scalar_one()
    assert occ.exception_chain is not None
    assert len(occ.exception_chain) == 2
    assert occ.exception_chain[0]["type"] == "ActiveRecord::RecordNotFound"
    assert occ.execution_context["type"] == "http"


@pytest.mark.asyncio
async def test_ingest_error_without_new_fields_still_works(
    api_client,
    db_session: AsyncSession,
    factory,
):
    """Backwards compatible — old payload still returns 202."""
    org = await factory(OrganizationFactory)
    await factory(
        ProjectFactory, organization_id=org.id, api_key_hash=hash_api_key(_API_KEY)
    )
    response = await api_client.post(
        "/api/v1/errors",
        headers={"Authorization": f"Bearer {_API_KEY}"},
        json={"error_class": "E", "message": "m"},
    )
    assert response.status_code == 202

    result = await db_session.execute(select(ErrorOccurrence))
    occ = result.scalar_one()
    assert occ.exception_chain is None
    assert occ.execution_context is None


@pytest.mark.asyncio
async def test_ingest_error_rejects_oversized_exception_chain(
    api_client,
    factory,
):
    """Chain with >20 entries is rejected with 422."""
    org = await factory(OrganizationFactory)
    await factory(
        ProjectFactory, organization_id=org.id, api_key_hash=hash_api_key(_API_KEY)
    )
    chain = [{"type": f"E{i}", "value": "v"} for i in range(21)]
    response = await api_client.post(
        "/api/v1/errors",
        headers={"Authorization": f"Bearer {_API_KEY}"},
        json={"error_class": "E", "message": "m", "exception_chain": chain},
    )
    assert response.status_code == 422
