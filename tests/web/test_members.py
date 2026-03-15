"""Tests for /orgs/{org_slug}/members web routes."""

import pytest
from oopsie.models.membership import MemberRole

from tests.conftest import set_membership_role


@pytest.mark.asyncio
async def test_invite_member_redirects(authenticated_client, organization):
    """POST /orgs/{slug}/members/invite creates invitation and redirects."""
    # current_user is already admin in organization (via fixture)
    resp = await authenticated_client.post(
        f"/orgs/{organization.slug}/members/invite",
        data={"email": "new@example.com", "role": "member"},
    )
    assert resp.status_code in (200, 303)
    if resp.status_code == 303:
        assert f"/orgs/{organization.slug}/settings" in resp.headers["location"]


@pytest.mark.asyncio
async def test_invite_member_403_for_member_role(
    authenticated_client, current_user, organization, db_session
):
    """POST /orgs/{slug}/members/invite returns 403 for MEMBER-role user."""
    await set_membership_role(
        db_session, current_user.id, organization.id, MemberRole.member
    )

    resp = await authenticated_client.post(
        f"/orgs/{organization.slug}/members/invite",
        data={"email": "new@example.com", "role": "member"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_invite_with_owner_role_403_for_admin(authenticated_client, organization):
    """POST /orgs/{slug}/members/invite with role=owner returns 403 for ADMIN."""
    # current_user is already admin in organization (via fixture)
    resp = await authenticated_client.post(
        f"/orgs/{organization.slug}/members/invite",
        data={"email": "escalate@example.com", "role": "owner"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_revoke_invitation_redirects(authenticated_client, organization, factory):
    """POST /orgs/{slug}/members/invitations/{id}/revoke removes invitation."""
    from tests.factories import InvitationFactory

    # current_user is already admin in organization (via fixture)
    inv = await factory(
        InvitationFactory,
        organization_id=organization.id,
        email="torem@example.com",
    )

    resp = await authenticated_client.post(
        f"/orgs/{organization.slug}/members/invitations/{inv.id}/revoke"
    )
    assert resp.status_code == 303
    assert f"/orgs/{organization.slug}/settings" in resp.headers["location"]


@pytest.mark.asyncio
async def test_update_member_role_redirects(
    authenticated_client, current_user, organization, factory, db_session
):
    """POST /orgs/{slug}/members/{id}/role updates role and redirects (OWNER actor)."""
    from tests.factories import MembershipFactory, UserFactory

    # Actor must be OWNER to promote MEMBER -> ADMIN
    await set_membership_role(
        db_session, current_user.id, organization.id, MemberRole.owner
    )

    other = await factory(UserFactory)
    membership = await factory(
        MembershipFactory,
        organization_id=organization.id,
        user_id=other.id,
        role=MemberRole.member,
    )

    resp = await authenticated_client.post(
        f"/orgs/{organization.slug}/members/{membership.id}/role",
        data={"role": "admin"},
    )
    assert resp.status_code == 303
    assert f"/orgs/{organization.slug}/settings" in resp.headers["location"]


@pytest.mark.asyncio
async def test_update_role_403_when_admin_promotes_to_owner(
    authenticated_client, organization, factory
):
    """ADMIN cannot promote a MEMBER to OWNER via the web endpoint."""
    from tests.factories import MembershipFactory, UserFactory

    # current_user is already admin in organization (via fixture)
    other = await factory(UserFactory)
    membership = await factory(
        MembershipFactory,
        organization_id=organization.id,
        user_id=other.id,
        role=MemberRole.member,
    )

    resp = await authenticated_client.post(
        f"/orgs/{organization.slug}/members/{membership.id}/role",
        data={"role": "owner"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_remove_member_redirects(authenticated_client, organization, factory):
    """POST /orgs/{slug}/members/{id}/remove deletes membership and redirects."""
    from tests.factories import MembershipFactory, UserFactory

    # current_user is already admin in organization (via fixture)
    other = await factory(UserFactory)
    membership = await factory(
        MembershipFactory,
        organization_id=organization.id,
        user_id=other.id,
        role=MemberRole.member,
    )

    resp = await authenticated_client.post(
        f"/orgs/{organization.slug}/members/{membership.id}/remove"
    )
    assert resp.status_code == 303
    assert f"/orgs/{organization.slug}/settings" in resp.headers["location"]


@pytest.mark.asyncio
async def test_remove_owner_403_for_admin(authenticated_client, organization, factory):
    """ADMIN cannot remove an OWNER via the web endpoint."""
    from tests.factories import MembershipFactory, UserFactory

    # current_user is already admin in organization (via fixture)
    owner = await factory(UserFactory)
    membership = await factory(
        MembershipFactory,
        organization_id=organization.id,
        user_id=owner.id,
        role=MemberRole.owner,
    )

    resp = await authenticated_client.post(
        f"/orgs/{organization.slug}/members/{membership.id}/remove"
    )
    assert resp.status_code == 403
