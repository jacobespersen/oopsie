"""Tests for RBAC dependency injection (get_current_membership, require_role)."""

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from oopsie.api.deps import get_session
from oopsie.auth import create_access_token
from oopsie.models.membership import MemberRole
from sqlalchemy.ext.asyncio import AsyncSession


def _make_app(required_role: MemberRole, db_session: AsyncSession) -> FastAPI:
    """Helper: create a minimal FastAPI app with a role-protected endpoint."""
    from oopsie.api.deps import require_role

    test_app = FastAPI()

    async def override_get_session():
        yield db_session

    test_app.dependency_overrides[get_session] = override_get_session

    @test_app.get("/protected/{org_slug}")
    async def protected(
        membership=Depends(require_role(required_role)),
    ):
        return {"role": membership.role.value}

    return test_app


@pytest.mark.asyncio
async def test_get_current_membership_returns_membership(
    db_session: AsyncSession, factory
):
    """get_current_membership returns the user's membership for the given org."""
    from oopsie.api.deps import get_current_membership
    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory, slug="test-org")
    user = await factory(UserFactory)
    await factory(MembershipFactory, organization_id=org.id, user_id=user.id, role=MemberRole.ADMIN)

    membership = await get_current_membership("test-org", db_session, user)
    assert membership is not None
    assert membership.user_id == user.id
    assert membership.role == MemberRole.ADMIN


@pytest.mark.asyncio
async def test_get_current_membership_raises_403_when_not_member(
    db_session: AsyncSession, factory
):
    """get_current_membership raises 403 when user has no membership in the org."""
    from fastapi import HTTPException
    from oopsie.api.deps import get_current_membership
    from tests.factories import OrganizationFactory, UserFactory

    await factory(OrganizationFactory, slug="other-org")
    user = await factory(UserFactory)

    with pytest.raises(HTTPException) as exc:
        await get_current_membership("other-org", db_session, user)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_role_allows_sufficient_role(
    db_session: AsyncSession, factory, api_client
):
    """require_role allows access when user has the required role or higher."""
    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory, slug="my-org")
    user = await factory(UserFactory)
    await factory(MembershipFactory, organization_id=org.id, user_id=user.id, role=MemberRole.ADMIN)

    access_token = create_access_token(user.id, user.email)
    app = _make_app(MemberRole.MEMBER, db_session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/protected/my-org",
            cookies={"access_token": access_token},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_require_role_denies_insufficient_role(
    db_session: AsyncSession, factory, api_client
):
    """require_role returns 403 when user has insufficient role."""
    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory, slug="my-org2")
    user = await factory(UserFactory)
    await factory(MembershipFactory, organization_id=org.id, user_id=user.id, role=MemberRole.MEMBER)

    access_token = create_access_token(user.id, user.email)
    app = _make_app(MemberRole.OWNER, db_session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/protected/my-org2",
            cookies={"access_token": access_token},
        )
    assert resp.status_code == 403
