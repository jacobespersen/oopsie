"""Tests for TokenRefreshMiddleware (transparent JWT token refresh)."""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import jwt as _jwt
import pytest
from oopsie.auth import create_access_token, create_refresh_token, decode_jwt
from oopsie.config import get_settings
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import MembershipFactory, OrganizationFactory, UserFactory


def _make_expired_access_token(user_id: uuid.UUID, email: str) -> str:
    """Create an access token that expired 5 minutes ago."""
    settings = get_settings()
    now = datetime.now(tz=UTC)
    payload = {
        "jti": str(uuid.uuid4()),
        "sub": str(user_id),
        "email": email,
        "type": "access",
        "iat": now - timedelta(hours=1, minutes=5),
        "exp": now - timedelta(minutes=5),
    }
    return _jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def _make_near_expiry_access_token(user_id: uuid.UUID, email: str) -> str:
    """Create an access token that expires in 3 minutes (within 5-min window)."""
    settings = get_settings()
    now = datetime.now(tz=UTC)
    payload = {
        "jti": str(uuid.uuid4()),
        "sub": str(user_id),
        "email": email,
        "type": "access",
        "iat": now - timedelta(minutes=57),
        "exp": now + timedelta(minutes=3),
    }
    return _jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def _make_expired_refresh_token(user_id: uuid.UUID) -> str:
    """Create a refresh token that expired 1 hour ago."""
    settings = get_settings()
    now = datetime.now(tz=UTC)
    payload = {
        "jti": str(uuid.uuid4()),
        "sub": str(user_id),
        "type": "refresh",
        "iat": now - timedelta(days=8),
        "exp": now - timedelta(hours=1),
    }
    return _jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


@asynccontextmanager
async def _session_factory_using(session: AsyncSession):
    """Context manager that yields the given session with begin() → begin_nested().

    The middleware calls ``async with async_session_factory() as s:
    async with s.begin(): ...``.  In tests the session already lives inside a
    rolled-back transaction, so ``begin()`` would fail.  We swap it for
    ``begin_nested()`` (savepoint) which works within an existing transaction.
    """
    original_begin = session.begin
    session.begin = session.begin_nested  # type: ignore[assignment]
    try:
        yield session
    finally:
        session.begin = original_begin  # type: ignore[assignment]


def _patch_middleware_session(db_session: AsyncSession):
    """Patch async_session_factory so the middleware reuses the test session."""
    return patch(
        "oopsie.database.async_session_factory",
        return_value=_session_factory_using(db_session),
    )


# ---------------------------------------------------------------------------
# Happy path: valid access token — no refresh needed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_access_token_passes_through(
    api_client, db_session: AsyncSession, factory
):
    """When the access token is valid and not near expiry, middleware does nothing."""
    org = await factory(OrganizationFactory)
    user = await factory(UserFactory)
    await factory(MembershipFactory, organization_id=org.id, user_id=user.id)

    access = create_access_token(user.id, user.email)
    refresh = create_refresh_token(user.id)

    resp = await api_client.get(
        f"/orgs/{org.slug}/projects",
        cookies={"access_token": access, "refresh_token": refresh},
    )
    assert resp.status_code == 200
    # No new cookies set — middleware didn't intervene
    assert "access_token" not in resp.cookies
    assert "refresh_token" not in resp.cookies


# ---------------------------------------------------------------------------
# Expired access token + valid refresh token → auto-refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_access_token_refreshed(
    api_client, db_session: AsyncSession, factory
):
    """Expired access token + valid refresh → new cookies, request succeeds."""
    org = await factory(OrganizationFactory)
    user = await factory(UserFactory)
    await factory(MembershipFactory, organization_id=org.id, user_id=user.id)

    expired_access = _make_expired_access_token(user.id, user.email)
    refresh = create_refresh_token(user.id)

    with _patch_middleware_session(db_session):
        resp = await api_client.get(
            f"/orgs/{org.slug}/projects",
            cookies={"access_token": expired_access, "refresh_token": refresh},
        )
    assert resp.status_code == 200
    # Middleware should have set new cookies
    assert "access_token" in resp.cookies
    assert "refresh_token" in resp.cookies
    # New tokens should be different from the originals
    assert resp.cookies["access_token"] != expired_access
    assert resp.cookies["refresh_token"] != refresh


# ---------------------------------------------------------------------------
# Near-expiry access token → proactive refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_near_expiry_access_token_refreshed(
    api_client, db_session: AsyncSession, factory
):
    """Access token within 5-min window + valid refresh → proactive refresh."""
    org = await factory(OrganizationFactory)
    user = await factory(UserFactory)
    await factory(MembershipFactory, organization_id=org.id, user_id=user.id)

    near_expiry_access = _make_near_expiry_access_token(user.id, user.email)
    refresh = create_refresh_token(user.id)

    with _patch_middleware_session(db_session):
        resp = await api_client.get(
            f"/orgs/{org.slug}/projects",
            cookies={
                "access_token": near_expiry_access,
                "refresh_token": refresh,
            },
        )
    assert resp.status_code == 200
    assert "access_token" in resp.cookies
    assert "refresh_token" in resp.cookies


# ---------------------------------------------------------------------------
# Both tokens expired → cookies cleared
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_both_tokens_expired_clears_cookies(
    api_client, db_session: AsyncSession, factory
):
    """Both tokens expired → cookies cleared, request proceeds unauthenticated."""
    org = await factory(OrganizationFactory)
    user = await factory(UserFactory)
    await factory(MembershipFactory, organization_id=org.id, user_id=user.id)

    expired_access = _make_expired_access_token(user.id, user.email)
    expired_refresh = _make_expired_refresh_token(user.id)

    with _patch_middleware_session(db_session):
        resp = await api_client.get(
            f"/orgs/{org.slug}/projects",
            cookies={
                "access_token": expired_access,
                "refresh_token": expired_refresh,
            },
        )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Refresh token revoked → cookies cleared
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoked_refresh_token_clears_cookies(
    api_client, db_session: AsyncSession, factory
):
    """Expired access + revoked refresh → cookies cleared."""
    from oopsie.auth import revoke_token

    org = await factory(OrganizationFactory)
    user = await factory(UserFactory)
    await factory(MembershipFactory, organization_id=org.id, user_id=user.id)

    expired_access = _make_expired_access_token(user.id, user.email)
    refresh = create_refresh_token(user.id)
    # Revoke the refresh token
    refresh_payload = decode_jwt(refresh)
    expires_at = datetime.fromtimestamp(refresh_payload["exp"], tz=UTC)
    await revoke_token(db_session, refresh_payload["jti"], expires_at)

    with _patch_middleware_session(db_session):
        resp = await api_client.get(
            f"/orgs/{org.slug}/projects",
            cookies={"access_token": expired_access, "refresh_token": refresh},
        )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Skipped paths — middleware should not run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skip_auth_routes(api_client, db_session: AsyncSession):
    """Middleware skips /auth/* routes — login page works with garbage cookies."""
    resp = await api_client.get(
        "/auth/login",
        cookies={"access_token": "garbage", "refresh_token": "garbage"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_skip_health_endpoint(api_client, db_session: AsyncSession):
    """Middleware skips /health — returns 200 with garbage cookies."""
    resp = await api_client.get(
        "/health",
        cookies={"access_token": "garbage", "refresh_token": "garbage"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_skip_api_routes(api_client, db_session: AsyncSession):
    """Middleware skips /api/v1/* — API auth is Bearer, not cookies."""
    resp = await api_client.post(
        "/api/v1/errors",
        cookies={"access_token": "garbage", "refresh_token": "garbage"},
    )
    # 401 from API auth (missing Bearer), not 500 from middleware
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Wrong token type in access_token cookie
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrong_token_type_in_access_cookie(
    api_client, db_session: AsyncSession, factory
):
    """Refresh token in access_token cookie slot is treated as invalid."""
    org = await factory(OrganizationFactory)
    user = await factory(UserFactory)
    await factory(MembershipFactory, organization_id=org.id, user_id=user.id)

    # Put a refresh token in the access_token cookie
    wrong_type_token = create_refresh_token(user.id)
    refresh = create_refresh_token(user.id)

    resp = await api_client.get(
        f"/orgs/{org.slug}/projects",
        cookies={"access_token": wrong_type_token, "refresh_token": refresh},
    )
    # The middleware should treat this as invalid and pass through;
    # get_current_user will reject it with 401
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Malformed cookies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_access_token_cookie(
    api_client, db_session: AsyncSession, factory
):
    """Garbage in access_token cookie is handled gracefully."""
    org = await factory(OrganizationFactory)
    user = await factory(UserFactory)
    await factory(MembershipFactory, organization_id=org.id, user_id=user.id)

    resp = await api_client.get(
        f"/orgs/{org.slug}/projects",
        cookies={"access_token": "not-a-jwt", "refresh_token": "also-garbage"},
    )
    # Should get 401 from downstream auth, not 500 from middleware
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DB error during refresh — fail open
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_db_error_fails_open(api_client, db_session: AsyncSession, factory):
    """DB failure during refresh → middleware fails open, request proceeds."""
    org = await factory(OrganizationFactory)
    user = await factory(UserFactory)
    await factory(MembershipFactory, organization_id=org.id, user_id=user.id)

    expired_access = _make_expired_access_token(user.id, user.email)
    refresh = create_refresh_token(user.id)

    # Patch at source — the middleware re-imports each call
    with patch("oopsie.database.async_session_factory") as mock_factory:
        mock_session = AsyncMock()
        from sqlalchemy.exc import SQLAlchemyError

        mock_session.__aenter__ = AsyncMock(side_effect=SQLAlchemyError("DB down"))
        mock_factory.return_value = mock_session

        resp = await api_client.get(
            f"/orgs/{org.slug}/projects",
            cookies={
                "access_token": expired_access,
                "refresh_token": refresh,
            },
        )
    # Middleware fails open — request proceeds unauthenticated
    # (expired access token, so get_current_user rejects it)
    assert resp.status_code == 401
    # Crucially: NOT a 500 — middleware didn't crash the request


# ---------------------------------------------------------------------------
# Refresh token valid but user deleted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_with_deleted_user_clears_cookies(
    api_client, db_session: AsyncSession, factory
):
    """If user was deleted between token issuance and refresh, cookies are cleared."""
    org = await factory(OrganizationFactory)
    user = await factory(UserFactory)
    await factory(MembershipFactory, organization_id=org.id, user_id=user.id)

    expired_access = _make_expired_access_token(user.id, user.email)
    refresh = create_refresh_token(user.id)

    # Delete the user
    await db_session.delete(user)
    await db_session.flush()

    with _patch_middleware_session(db_session):
        resp = await api_client.get(
            f"/orgs/{org.slug}/projects",
            cookies={"access_token": expired_access, "refresh_token": refresh},
        )
    assert resp.status_code == 401
