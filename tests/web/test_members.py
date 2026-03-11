"""Tests for /orgs/{org_slug}/members web routes."""

import pytest
from oopsie.models.membership import MemberRole


@pytest.mark.asyncio
async def test_invite_member_redirects(authenticated_client, current_user, factory):
    """POST /orgs/{slug}/members/invite creates invitation and redirects."""

    from tests.factories import MembershipFactory, OrganizationFactory

    org = await factory(OrganizationFactory, slug="invite-co")
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=current_user.id,
        role=MemberRole.admin,
    )

    resp = await authenticated_client.post(
        "/orgs/invite-co/members/invite",
        data={"email": "new@example.com", "role": "member"},
    )
    assert resp.status_code in (200, 303)
    if resp.status_code == 303:
        assert "/orgs/invite-co/settings" in resp.headers["location"]


@pytest.mark.asyncio
async def test_invite_member_403_for_member_role(
    authenticated_client, current_user, factory
):
    """POST /orgs/{slug}/members/invite returns 403 for MEMBER-role user."""
    from tests.factories import MembershipFactory, OrganizationFactory

    org = await factory(OrganizationFactory, slug="invite403-co")
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=current_user.id,
        role=MemberRole.member,
    )

    resp = await authenticated_client.post(
        "/orgs/invite403-co/members/invite",
        data={"email": "new@example.com", "role": "member"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_invite_with_owner_role_403_for_admin(
    authenticated_client, current_user, factory
):
    """POST /orgs/{slug}/members/invite with role=owner returns 403 for ADMIN."""
    from tests.factories import MembershipFactory, OrganizationFactory

    org = await factory(OrganizationFactory, slug="inv-owner-co")
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=current_user.id,
        role=MemberRole.admin,
    )

    resp = await authenticated_client.post(
        "/orgs/inv-owner-co/members/invite",
        data={"email": "escalate@example.com", "role": "owner"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_revoke_invitation_redirects(authenticated_client, current_user, factory):
    """POST /orgs/{slug}/members/invitations/{id}/revoke removes invitation."""
    from tests.factories import (
        InvitationFactory,
        MembershipFactory,
        OrganizationFactory,
    )

    org = await factory(OrganizationFactory, slug="revoke-co")
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=current_user.id,
        role=MemberRole.admin,
    )
    inv = await factory(
        InvitationFactory,
        organization_id=org.id,
        email="torem@example.com",
    )

    resp = await authenticated_client.post(
        f"/orgs/revoke-co/members/invitations/{inv.id}/revoke"
    )
    assert resp.status_code == 303
    assert "/orgs/revoke-co/settings" in resp.headers["location"]


@pytest.mark.asyncio
async def test_update_member_role_redirects(
    authenticated_client, current_user, factory
):
    """POST /orgs/{slug}/members/{id}/role updates role and redirects (OWNER actor)."""
    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory, slug="role-co")
    other = await factory(UserFactory)
    # Actor must be OWNER to promote MEMBER → ADMIN
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=current_user.id,
        role=MemberRole.owner,
    )
    membership = await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=other.id,
        role=MemberRole.member,
    )

    resp = await authenticated_client.post(
        f"/orgs/role-co/members/{membership.id}/role",
        data={"role": "admin"},
    )
    assert resp.status_code == 303
    assert "/orgs/role-co/settings" in resp.headers["location"]


@pytest.mark.asyncio
async def test_update_role_403_when_admin_promotes_to_owner(
    authenticated_client, current_user, factory
):
    """ADMIN cannot promote a MEMBER to OWNER via the web endpoint."""
    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory, slug="priv-esc-co")
    other = await factory(UserFactory)
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=current_user.id,
        role=MemberRole.admin,
    )
    membership = await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=other.id,
        role=MemberRole.member,
    )

    resp = await authenticated_client.post(
        f"/orgs/priv-esc-co/members/{membership.id}/role",
        data={"role": "owner"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_remove_member_redirects(authenticated_client, current_user, factory):
    """POST /orgs/{slug}/members/{id}/remove deletes membership and redirects."""
    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory, slug="rem-co")
    other = await factory(UserFactory)
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=current_user.id,
        role=MemberRole.admin,
    )
    membership = await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=other.id,
        role=MemberRole.member,
    )

    resp = await authenticated_client.post(
        f"/orgs/rem-co/members/{membership.id}/remove"
    )
    assert resp.status_code == 303
    assert "/orgs/rem-co/settings" in resp.headers["location"]


@pytest.mark.asyncio
async def test_remove_owner_403_for_admin(authenticated_client, current_user, factory):
    """ADMIN cannot remove an OWNER via the web endpoint."""
    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory, slug="rem-owner-co")
    owner = await factory(UserFactory)
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=current_user.id,
        role=MemberRole.admin,
    )
    membership = await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=owner.id,
        role=MemberRole.owner,
    )

    resp = await authenticated_client.post(
        f"/orgs/rem-owner-co/members/{membership.id}/remove"
    )
    assert resp.status_code == 403
