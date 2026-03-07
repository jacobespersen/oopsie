"""Tests for JWT auth, token revocation, user upsert, and OAuth routes."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from oopsie.auth import (
    create_access_token,
    create_refresh_token,
    decode_jwt,
    decode_jwt_token,
    revoke_token,
    upsert_user,
)
from oopsie.models.revoked_token import RevokedToken
from oopsie.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import UserFactory

# ---------------------------------------------------------------------------
# JWT creation
# ---------------------------------------------------------------------------


def test_create_access_token_structure():
    """Access token contains expected fields."""
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "test@example.com")
    payload = decode_jwt(token)
    assert payload["sub"] == str(user_id)
    assert payload["email"] == "test@example.com"
    assert payload["type"] == "access"
    assert "jti" in payload
    assert "exp" in payload
    assert "iat" in payload


def test_create_refresh_token_structure():
    """Refresh token contains expected fields."""
    user_id = uuid.uuid4()
    token = create_refresh_token(user_id)
    payload = decode_jwt(token)
    assert payload["sub"] == str(user_id)
    assert payload["type"] == "refresh"
    assert "jti" in payload
    assert "exp" in payload


def test_access_and_refresh_tokens_have_different_expiry():
    """Access token expires sooner than refresh token."""
    user_id = uuid.uuid4()
    access = decode_jwt(create_access_token(user_id, "a@b.com"))
    refresh = decode_jwt(create_refresh_token(user_id))
    assert access["exp"] < refresh["exp"]


def test_each_token_has_unique_jti():
    """Two tokens for the same user have different JTIs."""
    user_id = uuid.uuid4()
    t1 = decode_jwt(create_access_token(user_id, "a@b.com"))
    t2 = decode_jwt(create_access_token(user_id, "a@b.com"))
    assert t1["jti"] != t2["jti"]


# ---------------------------------------------------------------------------
# JWT decode (pure — no DB)
# ---------------------------------------------------------------------------


def test_decode_jwt_valid():
    """decode_jwt succeeds on a valid token."""
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "x@y.com")
    payload = decode_jwt(token)
    assert payload["sub"] == str(user_id)


def test_decode_jwt_expired():
    """decode_jwt raises ValueError on an expired token."""
    import jwt as _jwt
    from oopsie.config import get_settings

    settings = get_settings()
    now = datetime.now(tz=UTC)
    payload = {
        "jti": str(uuid.uuid4()),
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),
    }
    token = _jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    with pytest.raises(ValueError, match="expired"):
        decode_jwt(token)


def test_decode_jwt_invalid_signature():
    """decode_jwt raises ValueError for a tampered token."""
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "a@b.com")
    tampered = token[:-4] + "xxxx"
    with pytest.raises(ValueError):
        decode_jwt(tampered)


# ---------------------------------------------------------------------------
# Token revocation (requires DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_token_creates_deny_list_entry(db_session: AsyncSession):
    """revoke_token persists a RevokedToken row."""
    jti = str(uuid.uuid4())
    expires_at = datetime.now(tz=UTC) + timedelta(hours=1)
    await revoke_token(db_session, jti, expires_at)

    from sqlalchemy import select

    result = await db_session.execute(
        select(RevokedToken).where(RevokedToken.jti == jti)
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.jti == jti


@pytest.mark.asyncio
async def test_decode_jwt_token_passes_valid(db_session: AsyncSession):
    """decode_jwt_token succeeds for a non-revoked token."""
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "ok@example.com")
    payload = await decode_jwt_token(token, db_session)
    assert payload["sub"] == str(user_id)


@pytest.mark.asyncio
async def test_decode_jwt_token_rejects_revoked(db_session: AsyncSession):
    """decode_jwt_token raises ValueError when the JTI is in the deny list."""
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "revoked@example.com")
    payload = decode_jwt(token)
    expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
    await revoke_token(db_session, payload["jti"], expires_at)

    with pytest.raises(ValueError, match="revoked"):
        await decode_jwt_token(token, db_session)


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
async def test_auth_callback_success(api_client, db_session: AsyncSession, factory):
    """POST /auth/callback creates user and sets cookies on success (requires invitation)."""
    from tests.factories import InvitationFactory, OrganizationFactory

    org = await factory(OrganizationFactory)
    await factory(InvitationFactory, organization_id=org.id, email="callback@example.com")

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

    assert resp.status_code == 303
    assert resp.headers["location"] == f"/orgs/{org.slug}/projects"
    assert "access_token" in resp.cookies
    assert "refresh_token" in resp.cookies


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
    """POST /auth/logout clears auth cookies."""
    resp = await authenticated_client.post("/auth/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/login"
    # Cookies should be cleared (set to empty or deleted)
    assert resp.cookies.get("access_token", "") == ""


@pytest.mark.asyncio
async def test_logout_revokes_tokens(authenticated_client, db_session: AsyncSession):
    """POST /auth/logout adds the token JTI to the deny list."""
    from sqlalchemy import select

    resp = await authenticated_client.post("/auth/logout", follow_redirects=False)
    assert resp.status_code == 303

    result = await db_session.execute(select(RevokedToken))
    revoked = result.scalars().all()
    # At least the access token should be revoked
    assert len(revoked) >= 1


@pytest.mark.asyncio
async def test_refresh_issues_new_tokens(api_client, db_session: AsyncSession, factory):
    """POST /auth/refresh returns new tokens and revokes old refresh token."""
    from tests.factories import UserFactory

    user = await factory(UserFactory)
    refresh_token = create_refresh_token(user.id)

    resp = await api_client.post(
        "/auth/refresh", cookies={"refresh_token": refresh_token}
    )
    assert resp.status_code == 200
    assert "access_token" in resp.cookies
    assert "refresh_token" in resp.cookies
    new_refresh = resp.cookies["refresh_token"]
    assert new_refresh != refresh_token


@pytest.mark.asyncio
async def test_refresh_revokes_old_token(api_client, db_session: AsyncSession, factory):
    """Reusing an old refresh token after rotation returns 401."""
    from tests.factories import UserFactory

    user = await factory(UserFactory)
    old_refresh = create_refresh_token(user.id)

    # First refresh succeeds and rotates the token
    resp = await api_client.post(
        "/auth/refresh", cookies={"refresh_token": old_refresh}
    )
    assert resp.status_code == 200

    # Reusing the old refresh token should fail (it was revoked)
    resp2 = await api_client.post(
        "/auth/refresh", cookies={"refresh_token": old_refresh}
    )
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_refresh_without_cookie_fails(api_client):
    """POST /auth/refresh returns 401 when no refresh token cookie is present."""
    resp = await api_client.post("/auth/refresh")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_with_access_token_fails(api_client, factory):
    """POST /auth/refresh rejects an access token (wrong type)."""
    from tests.factories import UserFactory

    user = await factory(UserFactory)
    access_token = create_access_token(user.id, user.email)
    resp = await api_client.post(
        "/auth/refresh", cookies={"refresh_token": access_token}
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# get_current_user dependency (via project endpoints as proxy)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_request_returns_401(api_client):
    """Accessing a protected endpoint without auth returns 401."""
    resp = await api_client.get("/api/v1/orgs/test-org/projects")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_via_cookie(authenticated_client, organization):
    """Authenticated client can reach protected endpoints."""
    resp = await authenticated_client.get(f"/api/v1/orgs/{organization.slug}/projects")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_authenticated_via_bearer_header(api_client, factory):
    """Bearer token in Authorization header is accepted."""
    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory)
    user = await factory(UserFactory)
    await factory(MembershipFactory, organization_id=org.id, user_id=user.id)
    token = create_access_token(user.id, user.email)
    resp = await api_client.get(
        f"/api/v1/orgs/{org.slug}/projects",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_revoked_access_token_returns_401(
    api_client, db_session: AsyncSession, factory
):
    """A revoked access token is rejected with 401."""
    from tests.factories import UserFactory

    user = await factory(UserFactory)
    token = create_access_token(user.id, user.email)
    payload = decode_jwt(token)
    expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
    await revoke_token(db_session, payload["jti"], expires_at)

    resp = await api_client.get(
        "/api/v1/orgs/test-org/projects", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


def test_jwt_secret_required_when_google_configured():
    """Settings raises ValueError when Google OAuth is configured without JWT secret."""
    from oopsie.config import Settings
    from pydantic import ValidationError

    with pytest.raises((ValueError, ValidationError)):
        Settings(
            database_url="postgresql+asyncpg://localhost/test",
            google_client_id="some-client-id",
            google_client_secret="some-secret",
            jwt_secret_key="",
        )


def test_jwt_secret_too_short():
    """Settings raises ValueError when JWT secret is shorter than 32 characters."""
    from oopsie.config import Settings
    from pydantic import ValidationError

    with pytest.raises((ValueError, ValidationError)):
        Settings(
            database_url="postgresql+asyncpg://localhost/test",
            google_client_id="some-client-id",
            jwt_secret_key="tooshort",
        )


def test_jwt_secret_not_required_without_google():
    """Settings is valid without Google OAuth, even when JWT secret is empty."""
    from oopsie.config import Settings

    # Should not raise
    s = Settings(
        database_url="postgresql+asyncpg://localhost/test",
        google_client_id="",
        jwt_secret_key="",
    )
    assert s.google_client_id == ""


# ---------------------------------------------------------------------------
# Invitation-gated registration helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_invitation_found(db_session: AsyncSession, factory):
    """get_invitation returns invitation when one exists for the email."""
    from oopsie.auth import get_invitation

    from tests.factories import InvitationFactory, OrganizationFactory

    org = await factory(OrganizationFactory)
    inv = await factory(InvitationFactory, organization_id=org.id, email="invited@example.com")

    result = await get_invitation(db_session, "invited@example.com")
    assert result is not None
    assert result.id == inv.id


@pytest.mark.asyncio
async def test_get_invitation_not_found(db_session: AsyncSession):
    """get_invitation returns None when no invitation exists."""
    from oopsie.auth import get_invitation

    result = await get_invitation(db_session, "unknown@example.com")
    assert result is None


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
    api_client, db_session: AsyncSession, factory
):
    """New user with a pending invitation is logged in and membership created."""
    from oopsie.models.membership import Membership
    from sqlalchemy import select

    from tests.factories import InvitationFactory, OrganizationFactory

    org = await factory(OrganizationFactory)
    await factory(InvitationFactory, organization_id=org.id, email="new-invited@example.com")

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

    assert resp.status_code == 303
    assert resp.headers["location"] == f"/orgs/{org.slug}/projects"
    assert "access_token" in resp.cookies

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
    api_client, db_session: AsyncSession, factory
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

    assert resp.status_code == 303
    assert resp.headers["location"] == f"/orgs/{org.slug}/projects"
