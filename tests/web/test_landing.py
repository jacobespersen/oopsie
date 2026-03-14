"""Tests for the public landing page and signup request form."""

import pytest
from oopsie.models.signup_request import SignupRequest, SignupRequestStatus
from sqlalchemy import select

from tests.factories import SignupRequestFactory


@pytest.mark.asyncio
async def test_landing_page_loads(api_client):
    """GET / returns the landing page."""
    resp = await api_client.get("/")
    assert resp.status_code == 200
    assert "Request Access" in resp.text


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
