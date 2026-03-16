"""Tests for the platform admin signup request management."""

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from oopsie.main import app
from oopsie.models.signup_request import SignupRequestStatus
from oopsie.routers.dependencies import get_session
from oopsie.session import create_session

from tests.factories import SignupRequestFactory, UserFactory

# Reviewed fields required by the CHECK constraint for non-pending requests
_REVIEWED_AT = datetime(2026, 1, 1, tzinfo=UTC)


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


async def test_reject_requires_platform_admin(
    authenticated_client, current_user, db_session, factory
):
    """POST .../reject returns 403 for non-admin user."""
    sr = await factory(SignupRequestFactory)
    resp = await authenticated_client.post(
        f"/admin/signup-requests/{sr.id}/reject",
        follow_redirects=False,
    )
    assert resp.status_code == 403


async def test_approve_not_found_returns_404(
    authenticated_client, current_user, db_session, factory
):
    """POST .../approve with non-existent ID returns 404."""
    current_user.is_platform_admin = True
    await db_session.flush()
    resp = await authenticated_client.post(
        f"/admin/signup-requests/{uuid.uuid4()}/approve",
        follow_redirects=False,
    )
    assert resp.status_code == 404


async def test_reject_not_found_returns_404(
    authenticated_client, current_user, db_session, factory
):
    """POST .../reject with non-existent ID returns 404."""
    current_user.is_platform_admin = True
    await db_session.flush()
    resp = await authenticated_client.post(
        f"/admin/signup-requests/{uuid.uuid4()}/reject",
        follow_redirects=False,
    )
    assert resp.status_code == 404


async def test_approve_already_approved_returns_409(
    authenticated_client, current_user, db_session, factory
):
    """POST .../approve on already-approved request returns 409."""
    current_user.is_platform_admin = True
    await db_session.flush()
    reviewer = await factory(UserFactory)
    sr = await factory(
        SignupRequestFactory,
        status=SignupRequestStatus.approved,
        reviewed_by_id=reviewer.id,
        reviewed_at=_REVIEWED_AT,
    )
    resp = await authenticated_client.post(
        f"/admin/signup-requests/{sr.id}/approve",
        follow_redirects=False,
    )
    assert resp.status_code == 409


async def test_reject_already_rejected_returns_409(
    authenticated_client, current_user, db_session, factory
):
    """POST .../reject on already-rejected request returns 409."""
    current_user.is_platform_admin = True
    await db_session.flush()
    reviewer = await factory(UserFactory)
    sr = await factory(
        SignupRequestFactory,
        status=SignupRequestStatus.rejected,
        reviewed_by_id=reviewer.id,
        reviewed_at=_REVIEWED_AT,
    )
    resp = await authenticated_client.post(
        f"/admin/signup-requests/{sr.id}/reject",
        follow_redirects=False,
    )
    assert resp.status_code == 409


async def test_invalid_status_query_param_returns_400(
    authenticated_client, current_user, db_session
):
    """GET /admin/signup-requests?status=bogus returns 400."""
    current_user.is_platform_admin = True
    await db_session.flush()
    resp = await authenticated_client.get("/admin/signup-requests?status=bogus")
    assert resp.status_code == 400


async def test_csrf_rejection_without_token(
    db_session, current_user, fake_redis, factory
):
    """POST to admin route without CSRF token returns 403."""
    current_user.is_platform_admin = True
    await db_session.flush()

    sr = await factory(SignupRequestFactory)

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    session_token = await create_session(current_user.id)
    try:
        transport = httpx.ASGITransport(app=app)
        # Client with session cookie but NO CSRF token
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            cookies={"session_id": session_token},
        ) as client:
            resp = await client.post(
                f"/admin/signup-requests/{sr.id}/approve",
                follow_redirects=False,
            )
            assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_admin_notification_dot_shown_when_pending_requests(
    authenticated_client, current_user, db_session, factory
):
    """Admin link shows notification dot when pending signup requests exist."""
    current_user.is_platform_admin = True
    await db_session.flush()

    await factory(SignupRequestFactory)

    resp = await authenticated_client.get("/admin/signup-requests")
    assert resp.status_code == 200
    assert "admin-notification-dot" in resp.text


@pytest.mark.asyncio
async def test_admin_notification_dot_hidden_when_no_pending_requests(
    authenticated_client, current_user, db_session
):
    """Admin link has no notification dot when no pending signup requests."""
    current_user.is_platform_admin = True
    await db_session.flush()

    resp = await authenticated_client.get("/admin/signup-requests")
    assert resp.status_code == 200
    assert "Admin" in resp.text
    assert "admin-notification-dot" not in resp.text
