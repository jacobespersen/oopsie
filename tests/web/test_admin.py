"""Tests for the platform admin signup request management."""

import pytest
from oopsie.models.signup_request import SignupRequestStatus

from tests.factories import SignupRequestFactory


@pytest.mark.asyncio
async def test_admin_page_requires_auth(api_client):
    """GET /admin/signup-requests without auth returns 401."""
    resp = await api_client.get("/admin/signup-requests")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_page_requires_platform_admin(authenticated_client, current_user):
    """GET /admin/signup-requests without platform admin returns 403."""
    resp = await authenticated_client.get("/admin/signup-requests")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_page_loads_for_platform_admin(
    authenticated_client, current_user, db_session, factory
):
    """GET /admin/signup-requests loads for platform admin."""
    current_user.is_platform_admin = True
    await db_session.flush()

    await factory(SignupRequestFactory)

    resp = await authenticated_client.get("/admin/signup-requests")
    assert resp.status_code == 200
    assert "Signup Requests" in resp.text


@pytest.mark.asyncio
async def test_approve_signup_request_action(
    authenticated_client, current_user, db_session, factory
):
    """POST /admin/signup-requests/{id}/approve approves and redirects."""
    current_user.is_platform_admin = True
    await db_session.flush()

    sr = await factory(SignupRequestFactory)
    resp = await authenticated_client.post(
        f"/admin/signup-requests/{sr.id}/approve",
        follow_redirects=False,
    )
    assert resp.status_code == 303

    await db_session.refresh(sr)
    assert sr.status == SignupRequestStatus.approved


@pytest.mark.asyncio
async def test_reject_signup_request_action(
    authenticated_client, current_user, db_session, factory
):
    """POST /admin/signup-requests/{id}/reject rejects and redirects."""
    current_user.is_platform_admin = True
    await db_session.flush()

    sr = await factory(SignupRequestFactory)
    resp = await authenticated_client.post(
        f"/admin/signup-requests/{sr.id}/reject",
        follow_redirects=False,
    )
    assert resp.status_code == 303

    await db_session.refresh(sr)
    assert sr.status == SignupRequestStatus.rejected


@pytest.mark.asyncio
async def test_approve_requires_platform_admin(
    authenticated_client, current_user, db_session, factory
):
    """POST /admin/signup-requests/{id}/approve returns 403 for non-admin."""
    sr = await factory(SignupRequestFactory)
    resp = await authenticated_client.post(
        f"/admin/signup-requests/{sr.id}/approve",
        follow_redirects=False,
    )
    assert resp.status_code == 403
