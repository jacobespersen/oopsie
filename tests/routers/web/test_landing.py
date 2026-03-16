"""Tests for the public landing page and signup request form."""

from unittest.mock import AsyncMock

import httpx
import pytest
from oopsie.database import get_session
from oopsie.main import app
from oopsie.models.signup_request import SignupRequest, SignupRequestStatus
from oopsie.session import create_session
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import SignupRequestFactory, UserFactory


@pytest.mark.asyncio
async def test_landing_page_loads(api_client):
    """GET / returns the landing page for unauthenticated users."""
    resp = await api_client.get("/")
    assert resp.status_code == 200
    assert "Request Access" in resp.text


@pytest.mark.asyncio
async def test_landing_page_redirects_authenticated_user(
    authenticated_client, organization
):
    """GET / redirects logged-in users to their org's projects page."""
    resp = await authenticated_client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == f"/orgs/{organization.slug}/projects"


@pytest.mark.asyncio
async def test_signup_request_form_submission(api_client, db_session):
    """POST /signup-request creates a pending signup request."""
    resp = await api_client.post(
        "/signup-request",
        data={
            "name": "Alice",
            "email": "alice@example.com",
            "org_name": "Alice Co",
            "reason": "I want to fix bugs",
        },
    )
    assert resp.status_code == 200
    assert "Request submitted" in resp.text

    result = await db_session.execute(
        select(SignupRequest).where(SignupRequest.email == "alice@example.com")
    )
    sr = result.scalar_one()
    assert sr.status == SignupRequestStatus.pending


@pytest.mark.asyncio
async def test_signup_request_duplicate_shows_error(api_client, db_session, factory):
    """POST /signup-request with duplicate pending email shows error."""
    await factory(SignupRequestFactory, email="dup@example.com")
    resp = await api_client.post(
        "/signup-request",
        data={
            "name": "Bob",
            "email": "dup@example.com",
            "org_name": "Bob Co",
            "reason": "Testing",
        },
    )
    assert resp.status_code == 200
    assert "already pending" in resp.text


@pytest.mark.asyncio
async def test_signup_request_invalid_email_shows_field_error(api_client):
    """POST /signup-request with invalid email shows field-level error."""
    resp = await api_client.post(
        "/signup-request",
        data={
            "name": "Alice",
            "email": "not-an-email",
            "org_name": "Alice Co",
            "reason": "I want to fix bugs",
        },
    )
    assert resp.status_code == 200
    assert "Request submitted" not in resp.text
    # Field-level error should appear for email
    assert "color-fg-danger" in resp.text


@pytest.mark.asyncio
async def test_signup_request_name_too_long_shows_field_error(api_client):
    """POST /signup-request with name exceeding 255 chars shows field error."""
    resp = await api_client.post(
        "/signup-request",
        data={
            "name": "A" * 256,
            "email": "alice@example.com",
            "org_name": "Alice Co",
            "reason": "I want to fix bugs",
        },
    )
    assert resp.status_code == 200
    assert "Request submitted" not in resp.text
    assert "color-fg-danger" in resp.text


@pytest.mark.asyncio
async def test_signup_request_reason_too_long_shows_field_error(api_client):
    """POST /signup-request with reason exceeding 2000 chars shows field error."""
    resp = await api_client.post(
        "/signup-request",
        data={
            "name": "Alice",
            "email": "alice@example.com",
            "org_name": "Alice Co",
            "reason": "x" * 2001,
        },
    )
    assert resp.status_code == 200
    assert "Request submitted" not in resp.text
    assert "color-fg-danger" in resp.text


@pytest.mark.asyncio
async def test_signup_request_preserves_form_data_on_validation_error(api_client):
    """POST /signup-request re-renders form with submitted values on error."""
    resp = await api_client.post(
        "/signup-request",
        data={
            "name": "Alice",
            "email": "bad-email",
            "org_name": "Alice Co",
            "reason": "Testing",
        },
    )
    assert resp.status_code == 200
    # Form values should be preserved in the re-rendered form
    assert "Alice" in resp.text
    assert "bad-email" in resp.text
    assert "Alice Co" in resp.text


@pytest.mark.asyncio
async def test_authenticated_user_without_membership_sees_landing(
    db_session: AsyncSession, fake_redis
):
    """Authenticated user with no org membership sees the landing page."""
    # Create a user with no membership (not using current_user fixture
    # which auto-creates a membership).
    user = UserFactory.build()
    db_session.add(user)
    await db_session.flush()

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    session_token = await create_session(user.id)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            cookies={"session_id": session_token},
        ) as client:
            resp = await client.get("/", follow_redirects=False)
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert resp.status_code == 200
    assert "Request Access" in resp.text


@pytest.mark.asyncio
async def test_redis_failure_falls_through_to_landing(
    db_session: AsyncSession, fake_redis
):
    """Redis failure during session lookup gracefully shows landing page."""

    async def override_get_session():
        yield db_session

    # Make the fake Redis raise on hget to simulate a connection failure.
    # get_session_user_id catches RedisError internally and returns None,
    # so the landing page should render normally.
    fake_redis.hget = AsyncMock(side_effect=RedisError("connection lost"))

    app.dependency_overrides[get_session] = override_get_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            cookies={"session_id": "some-token"},
        ) as client:
            resp = await client.get("/", follow_redirects=False)
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert resp.status_code == 200
    assert "Request Access" in resp.text
