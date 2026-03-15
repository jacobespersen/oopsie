"""Tests for RBAC dependency injection (get_authenticated_membership, RequireRole)."""

import uuid

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from oopsie.models.membership import MemberRole
from oopsie.routers.dependencies import get_session
from oopsie.session import create_session
from sqlalchemy.ext.asyncio import AsyncSession


def _make_app(required_role: MemberRole, db_session: AsyncSession) -> FastAPI:
    """Helper: create a minimal FastAPI app with a role-protected endpoint."""
    from oopsie.routers.dependencies import RequireRole

    test_app = FastAPI()

    async def override_get_session():
        yield db_session

    test_app.dependency_overrides[get_session] = override_get_session

    @test_app.get("/protected/{org_slug}")
    async def protected(
        membership=Depends(RequireRole(required_role)),
    ):
        return {
            "role": membership.role.value,
            "user_id": str(membership.user.id),
            "org_id": str(membership.organization.id),
        }

    return test_app


@pytest.mark.asyncio
async def test_get_current_membership_returns_membership(
    db_session: AsyncSession, factory
):
    """get_current_membership returns the user's membership for the given org."""
    from oopsie.routers.dependencies import get_current_membership

    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory, slug="test-org")
    user = await factory(UserFactory)
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=user.id,
        role=MemberRole.admin,
    )

    membership = await get_current_membership("test-org", db_session, user)
    assert membership is not None
    assert membership.user_id == user.id
    assert membership.role == MemberRole.admin


@pytest.mark.asyncio
async def test_get_current_membership_raises_403_when_not_member(
    db_session: AsyncSession, factory
):
    """get_current_membership raises 403 when user has no membership in the org."""
    from fastapi import HTTPException
    from oopsie.routers.dependencies import get_current_membership

    from tests.factories import OrganizationFactory, UserFactory

    await factory(OrganizationFactory, slug="other-org")
    user = await factory(UserFactory)

    with pytest.raises(HTTPException) as exc:
        await get_current_membership("other-org", db_session, user)
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# get_authenticated_membership
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_authenticated_membership_valid(
    db_session: AsyncSession, factory, fake_redis
):
    """Valid session + valid org returns membership with user and org populated."""
    from unittest.mock import MagicMock

    from oopsie.routers.dependencies import get_authenticated_membership

    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory, slug="auth-mem-org")
    user = await factory(UserFactory)
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=user.id,
        role=MemberRole.admin,
    )

    session_token = await create_session(user.id)
    request = MagicMock()
    request.cookies = {"session_id": session_token}

    membership = await get_authenticated_membership(request, "auth-mem-org", db_session)
    assert membership.user_id == user.id
    assert membership.user.id == user.id
    assert membership.organization.slug == "auth-mem-org"
    assert membership.role == MemberRole.admin


@pytest.mark.asyncio
async def test_get_authenticated_membership_no_session_returns_401(
    db_session: AsyncSession,
):
    """Missing session cookie returns 401."""
    from unittest.mock import MagicMock

    from fastapi import HTTPException
    from oopsie.routers.dependencies import get_authenticated_membership

    request = MagicMock()
    request.cookies = {}

    with pytest.raises(HTTPException) as exc:
        await get_authenticated_membership(request, "any-org", db_session)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_authenticated_membership_invalid_session_returns_401(
    db_session: AsyncSession, fake_redis
):
    """Invalid/expired session token returns 401."""
    from unittest.mock import MagicMock

    from fastapi import HTTPException
    from oopsie.routers.dependencies import get_authenticated_membership

    request = MagicMock()
    request.cookies = {"session_id": "invalid-token"}

    with pytest.raises(HTTPException) as exc:
        await get_authenticated_membership(request, "any-org", db_session)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_authenticated_membership_wrong_org_returns_403(
    db_session: AsyncSession, factory, fake_redis
):
    """Valid session + wrong org slug returns 403."""
    from unittest.mock import MagicMock

    from fastapi import HTTPException
    from oopsie.routers.dependencies import get_authenticated_membership

    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory, slug="right-org")
    await factory(OrganizationFactory, slug="wrong-org")
    user = await factory(UserFactory)
    await factory(MembershipFactory, organization_id=org.id, user_id=user.id)

    session_token = await create_session(user.id)
    request = MagicMock()
    request.cookies = {"session_id": session_token}

    with pytest.raises(HTTPException) as exc:
        await get_authenticated_membership(request, "wrong-org", db_session)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_authenticated_membership_deleted_user_returns_401(
    db_session: AsyncSession, fake_redis
):
    """Session pointing to non-existent user returns 401."""
    from unittest.mock import MagicMock

    from fastapi import HTTPException
    from oopsie.routers.dependencies import get_authenticated_membership

    # Create session for a user ID that doesn't exist in DB
    fake_user_id = uuid.uuid4()
    session_token = await create_session(fake_user_id)
    request = MagicMock()
    request.cookies = {"session_id": session_token}

    with pytest.raises(HTTPException) as exc:
        await get_authenticated_membership(request, "any-org", db_session)
    assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# RequireRole (integration via HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_role_allows_sufficient_role(
    db_session: AsyncSession, factory, api_client, fake_redis
):
    """RequireRole allows access when user has the required role or higher."""
    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory, slug="my-org")
    user = await factory(UserFactory)
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=user.id,
        role=MemberRole.admin,
    )

    session_token = await create_session(user.id)
    app = _make_app(MemberRole.member, db_session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/protected/my-org",
            cookies={"session_id": session_token},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "admin"
    assert data["user_id"] == str(user.id)
    assert data["org_id"] == str(org.id)


@pytest.mark.asyncio
async def test_require_role_denies_insufficient_role(
    db_session: AsyncSession, factory, api_client, fake_redis
):
    """RequireRole returns 403 when user has insufficient role."""
    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory, slug="my-org2")
    user = await factory(UserFactory)
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=user.id,
        role=MemberRole.member,
    )

    session_token = await create_session(user.id)
    app = _make_app(MemberRole.owner, db_session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/protected/my-org2",
            cookies={"session_id": session_token},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_require_role_populates_user_and_org(
    db_session: AsyncSession, factory, api_client, fake_redis
):
    """RequireRole returns membership with user and organization eagerly loaded."""
    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory, slug="eager-org")
    user = await factory(UserFactory)
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=user.id,
        role=MemberRole.member,
    )

    session_token = await create_session(user.id)
    app = _make_app(MemberRole.member, db_session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/protected/eager-org",
            cookies={"session_id": session_token},
        )
    assert resp.status_code == 200
    data = resp.json()
    # Verify user and org are populated (accessed in the endpoint handler)
    assert data["user_id"] == str(user.id)
    assert data["org_id"] == str(org.id)
