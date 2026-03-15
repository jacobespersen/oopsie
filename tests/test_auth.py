"""Tests for auth helpers, user upsert, and OAuth routes."""

from unittest.mock import AsyncMock, patch

import pytest
from oopsie.auth import upsert_user
from oopsie.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import UserFactory

# ---------------------------------------------------------------------------
# User upsert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_user_creates_new(db_session: AsyncSession):
    """upsert_user creates a new User on first call."""
    google_info = {
        "sub": "google-new-123",
        "email": "new@example.com",
        "name": "New User",
        "picture": "https://example.com/avatar.jpg",
    }
    user = await upsert_user(db_session, google_info)
    assert isinstance(user, User)
    assert user.email == "new@example.com"
    assert user.google_sub == "google-new-123"
    assert user.name == "New User"
    assert user.avatar_url == "https://example.com/avatar.jpg"
    assert user.id is not None


@pytest.mark.asyncio
async def test_upsert_user_updates_existing(db_session: AsyncSession):
    """upsert_user updates email/name/avatar for an existing user."""
    existing = UserFactory.build(google_sub="google-existing-456")
    db_session.add(existing)
    await db_session.flush()
    original_id = existing.id

    google_info = {
        "sub": "google-existing-456",
        "email": "updated@example.com",
        "name": "Updated Name",
        "picture": "https://example.com/new-avatar.jpg",
    }
    user = await upsert_user(db_session, google_info)
    assert user.id == original_id
    assert user.email == "updated@example.com"
    assert user.name == "Updated Name"
    assert user.avatar_url == "https://example.com/new-avatar.jpg"


@pytest.mark.asyncio
async def test_upsert_user_uses_email_as_name_fallback(db_session: AsyncSession):
    """upsert_user uses email as name when 'name' is absent."""
    google_info = {
        "sub": "google-noname-789",
        "email": "noname@example.com",
    }
    user = await upsert_user(db_session, google_info)
    assert user.name == "noname@example.com"


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_page_returns_200(api_client):
    """GET /auth/login renders the login page."""
    resp = await api_client.get("/auth/login")
    assert resp.status_code == 200
    assert b"Sign in" in resp.content


@pytest.mark.asyncio
async def test_login_google_unconfigured(api_client):
    """GET /auth/login/google returns 501 when Google OAuth is not configured."""
    from unittest.mock import MagicMock

    mock_cfg = MagicMock()
    mock_cfg.google_client_id = ""
    with patch("oopsie.auth_routes.get_settings", return_value=mock_cfg):
        resp = await api_client.get("/auth/login/google", follow_redirects=False)
    assert resp.status_code == 501


@pytest.mark.asyncio
async def test_auth_callback_success(
    api_client, db_session: AsyncSession, factory, fake_redis
):
    """Creates user and sets session cookie on success (requires invitation)."""
    from tests.factories import InvitationFactory, OrganizationFactory

    org = await factory(OrganizationFactory)
    await factory(
        InvitationFactory, organization_id=org.id, email="callback@example.com"
    )

    mock_google = AsyncMock()
    mock_google.authorize_access_token = AsyncMock(
        return_value={
            "userinfo": {
                "sub": "google-callback-sub",
                "email": "callback@example.com",
                "name": "Callback User",
            }
        }
    )
    with patch("oopsie.auth_routes.get_google_oauth_client", return_value=mock_google):
        resp = await api_client.get("/auth/callback", follow_redirects=False)

    assert resp.status_code == 200
    assert f"/orgs/{org.slug}/projects" in resp.text
    assert "session_id" in resp.cookies


@pytest.mark.asyncio
async def test_auth_callback_missing_userinfo(api_client):
    """POST /auth/callback returns 400 when Google returns no userinfo."""
    mock_google = AsyncMock()
    mock_google.authorize_access_token = AsyncMock(return_value={})
    with patch("oopsie.auth_routes.get_google_oauth_client", return_value=mock_google):
        resp = await api_client.get("/auth/callback")

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_logout_clears_cookies(authenticated_client):
    """POST /auth/logout clears the session cookie."""
    resp = await authenticated_client.post("/auth/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/login"
    # Cookie should be cleared (set to empty or deleted)
    assert resp.cookies.get("session_id", "") == ""


@pytest.mark.asyncio
async def test_logout_deletes_session_from_redis(authenticated_client, fake_redis):
    """POST /auth/logout removes the session from Redis."""
    # The authenticated_client has a session_id cookie backed by fake_redis.
    # After logout, the session key should no longer exist in Redis.
    session_token = authenticated_client.cookies.get("session_id")
    assert session_token is not None

    # Verify the session exists before logout (stored as a Redis hash)
    value = await fake_redis.hget(f"session:{session_token}", "user_id")
    assert value is not None

    resp = await authenticated_client.post("/auth/logout", follow_redirects=False)
    assert resp.status_code == 303

    # Session should be gone from Redis
    value = await fake_redis.hget(f"session:{session_token}", "user_id")
    assert value is None


# ---------------------------------------------------------------------------
# get_current_user dependency (via project endpoints as proxy)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_request_returns_401(api_client):
    """Accessing a protected endpoint without auth returns 401."""
    resp = await api_client.get("/orgs/test-org/projects")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_via_cookie(authenticated_client, organization):
    """Authenticated client can reach protected endpoints."""
    resp = await authenticated_client.get(f"/orgs/{organization.slug}/projects")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Invitation-gated registration helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pending_invitations_found(db_session: AsyncSession, factory):
    """get_pending_invitations returns invitations for the email."""
    from oopsie.auth import get_pending_invitations

    from tests.factories import InvitationFactory, OrganizationFactory

    org = await factory(OrganizationFactory)
    inv = await factory(
        InvitationFactory, organization_id=org.id, email="invited@example.com"
    )

    results = await get_pending_invitations(db_session, "invited@example.com")
    assert len(results) == 1
    assert results[0].id == inv.id


@pytest.mark.asyncio
async def test_get_pending_invitations_not_found(db_session: AsyncSession):
    """get_pending_invitations returns empty list when no invitation exists."""
    from oopsie.auth import get_pending_invitations

    results = await get_pending_invitations(db_session, "unknown@example.com")
    assert results == []


@pytest.mark.asyncio
async def test_accept_invitation_creates_membership(db_session: AsyncSession, factory):
    """accept_invitation deletes the invitation and creates a Membership."""
    from oopsie.auth import accept_invitation
    from oopsie.models.invitation import Invitation
    from oopsie.models.membership import Membership
    from sqlalchemy import select

    from tests.factories import InvitationFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory)
    user = await factory(UserFactory)
    inv = await factory(InvitationFactory, organization_id=org.id, email=user.email)
    inv_id = inv.id
    inv_role = inv.role

    await accept_invitation(db_session, inv, user)
    await db_session.flush()

    # Invitation should be deleted
    remaining = await db_session.scalar(
        select(Invitation).where(Invitation.id == inv_id)
    )
    assert remaining is None

    # Membership should be created
    result = await db_session.execute(select(Membership))
    memberships = result.scalars().all()
    assert len(memberships) == 1
    assert memberships[0].user_id == user.id
    assert memberships[0].organization_id == org.id
    assert memberships[0].role == inv_role


# ---------------------------------------------------------------------------
# Invitation-gated auth callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_callback_new_user_with_invitation_succeeds(
    api_client, db_session: AsyncSession, factory, fake_redis
):
    """New user with a pending invitation is logged in and membership created."""
    from oopsie.models.membership import Membership
    from sqlalchemy import select

    from tests.factories import InvitationFactory, OrganizationFactory

    org = await factory(OrganizationFactory)
    await factory(
        InvitationFactory, organization_id=org.id, email="new-invited@example.com"
    )

    mock_google = AsyncMock()
    mock_google.authorize_access_token = AsyncMock(
        return_value={
            "userinfo": {
                "sub": "google-new-invited-sub",
                "email": "new-invited@example.com",
                "name": "New Invited User",
            }
        }
    )
    with patch("oopsie.auth_routes.get_google_oauth_client", return_value=mock_google):
        resp = await api_client.get("/auth/callback", follow_redirects=False)

    assert resp.status_code == 200
    assert f"/orgs/{org.slug}/projects" in resp.text
    assert "session_id" in resp.cookies

    memberships = (await db_session.execute(select(Membership))).scalars().all()
    assert len(memberships) == 1


@pytest.mark.asyncio
async def test_auth_callback_new_user_without_invitation_redirects(api_client):
    """New user with no invitation is redirected to login with error."""
    mock_google = AsyncMock()
    mock_google.authorize_access_token = AsyncMock(
        return_value={
            "userinfo": {
                "sub": "google-no-invite-sub",
                "email": "no-invite@example.com",
                "name": "No Invite User",
            }
        }
    )
    with patch("oopsie.auth_routes.get_google_oauth_client", return_value=mock_google):
        resp = await api_client.get("/auth/callback", follow_redirects=False)

    assert resp.status_code == 303
    assert "no_invitation" in resp.headers["location"]


@pytest.mark.asyncio
async def test_auth_callback_existing_user_bypasses_invitation(
    api_client, db_session: AsyncSession, factory, fake_redis
):
    """Existing user (already in DB) can log in without an invitation."""
    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory)
    user = await factory(UserFactory, google_sub="google-existing-bypass")
    await factory(MembershipFactory, organization_id=org.id, user_id=user.id)

    mock_google = AsyncMock()
    mock_google.authorize_access_token = AsyncMock(
        return_value={
            "userinfo": {
                "sub": "google-existing-bypass",
                "email": user.email,
                "name": user.name,
            }
        }
    )
    with patch("oopsie.auth_routes.get_google_oauth_client", return_value=mock_google):
        resp = await api_client.get("/auth/callback", follow_redirects=False)

    assert resp.status_code == 200
    assert f"/orgs/{org.slug}/projects" in resp.text


@pytest.mark.asyncio
async def test_auth_callback_only_accepts_first_invitation(
    api_client, db_session: AsyncSession, factory, fake_redis
):
    """New user with invitations from two orgs gets only one membership;
    the other invitation is deleted (single-org model)."""
    from oopsie.models.invitation import Invitation
    from oopsie.models.membership import Membership
    from sqlalchemy import select

    from tests.factories import InvitationFactory, OrganizationFactory

    org1 = await factory(OrganizationFactory, slug="single-org-a")
    org2 = await factory(OrganizationFactory, slug="single-org-b")
    await factory(
        InvitationFactory, organization_id=org1.id, email="single-inv@example.com"
    )
    await factory(
        InvitationFactory, organization_id=org2.id, email="single-inv@example.com"
    )

    mock_google = AsyncMock()
    mock_google.authorize_access_token = AsyncMock(
        return_value={
            "userinfo": {
                "sub": "google-single-inv-sub",
                "email": "single-inv@example.com",
                "name": "Single Org User",
            }
        }
    )
    with patch("oopsie.auth_routes.get_google_oauth_client", return_value=mock_google):
        resp = await api_client.get("/auth/callback", follow_redirects=False)

    assert resp.status_code == 200
    assert "session_id" in resp.cookies

    # Only one membership should be created (single-org enforcement)
    memberships = (await db_session.execute(select(Membership))).scalars().all()
    assert len(memberships) == 1

    # The other invitation should have been deleted
    remaining = (await db_session.execute(select(Invitation))).scalars().all()
    assert len(remaining) == 0


# ---------------------------------------------------------------------------
# resolve_or_register_user: existing user skips invitation lookup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_existing_user_skips_invitation_lookup(
    db_session: AsyncSession, factory
):
    """Existing user login skips invitation query and returns user with memberships."""
    from oopsie.auth import resolve_or_register_user

    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory)
    user = await factory(UserFactory, google_sub="google-skip-inv")
    await factory(MembershipFactory, organization_id=org.id, user_id=user.id)

    google_info = {
        "sub": "google-skip-inv",
        "email": user.email,
        "name": user.name,
    }
    returned_user, new_membership = await resolve_or_register_user(
        db_session, google_info
    )
    assert returned_user.id == user.id
    # Existing users return no new membership (invitations not checked)
    assert new_membership is None
    # Memberships should be eagerly loaded on the user
    assert len(returned_user.memberships) == 1
    assert returned_user.memberships[0].organization.slug == org.slug


@pytest.mark.asyncio
async def test_resolve_existing_user_no_memberships_returns_empty(
    db_session: AsyncSession, factory
):
    """Existing user with no memberships returns None."""
    from oopsie.auth import resolve_or_register_user

    from tests.factories import UserFactory

    user = await factory(UserFactory, google_sub="google-no-mem")

    google_info = {
        "sub": "google-no-mem",
        "email": user.email,
        "name": user.name,
    }
    returned_user, new_membership = await resolve_or_register_user(
        db_session, google_info
    )
    assert returned_user.id == user.id
    assert new_membership is None
    assert len(returned_user.memberships) == 0


@pytest.mark.asyncio
async def test_auth_callback_existing_user_no_memberships_redirects_to_error(
    api_client, db_session: AsyncSession, factory, fake_redis
):
    """Existing user with no memberships redirects to login with error."""
    from tests.factories import UserFactory

    await factory(UserFactory, google_sub="google-no-mem-cb")

    mock_google = AsyncMock()
    mock_google.authorize_access_token = AsyncMock(
        return_value={
            "userinfo": {
                "sub": "google-no-mem-cb",
                "email": "nomem@example.com",
                "name": "No Membership User",
            }
        }
    )
    with patch("oopsie.auth_routes.get_google_oauth_client", return_value=mock_google):
        resp = await api_client.get("/auth/callback", follow_redirects=False)

    assert resp.status_code == 200
    assert "no_organization" in resp.text


@pytest.mark.asyncio
async def test_auth_callback_stores_org_slug_in_session(
    api_client, db_session: AsyncSession, factory, fake_redis
):
    """After login, the Redis session hash contains org_slug for the user's org."""
    from tests.factories import InvitationFactory, OrganizationFactory

    org = await factory(OrganizationFactory, slug="session-org")
    await factory(
        InvitationFactory, organization_id=org.id, email="session-test@example.com"
    )

    mock_google = AsyncMock()
    mock_google.authorize_access_token = AsyncMock(
        return_value={
            "userinfo": {
                "sub": "google-session-test-sub",
                "email": "session-test@example.com",
                "name": "Session Test User",
            }
        }
    )
    with patch("oopsie.auth_routes.get_google_oauth_client", return_value=mock_google):
        resp = await api_client.get("/auth/callback", follow_redirects=False)

    assert resp.status_code == 200
    session_token = resp.cookies["session_id"]

    # Verify org_slug is stored in the Redis session hash
    stored_slug = await fake_redis.hget(f"session:{session_token}", "org_slug")
    assert stored_slug is not None
    slug_value = stored_slug if isinstance(stored_slug, str) else stored_slug.decode()
    assert slug_value == "session-org"
