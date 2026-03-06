"""Tests for /orgs/{org_slug}/members web routes."""

import pytest
from oopsie.models.invitation import InvitationStatus
from oopsie.models.membership import MemberRole


@pytest.mark.asyncio
async def test_members_list_200(authenticated_client, current_user, factory):
    """GET /orgs/{slug}/members returns 200 for a member of the org."""
    from tests.factories import MembershipFactory, OrganizationFactory

    org = await factory(OrganizationFactory, slug="my-co")
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=current_user.id,
        role=MemberRole.ADMIN,
    )

    resp = await authenticated_client.get("/orgs/my-co/members")
    assert resp.status_code == 200
    assert "Members" in resp.text


@pytest.mark.asyncio
async def test_members_list_403_non_member(authenticated_client, factory):
    """GET /orgs/{slug}/members returns 403 if user has no membership."""
    from tests.factories import OrganizationFactory

    await factory(OrganizationFactory, slug="other-co")

    resp = await authenticated_client.get("/orgs/other-co/members")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_members_list_shows_members_and_invitations(
    authenticated_client, current_user, factory
):
    """Members page lists members and pending invitations."""
    from tests.factories import (
        InvitationFactory,
        MembershipFactory,
        OrganizationFactory,
        UserFactory,
    )

    org = await factory(OrganizationFactory, slug="show-co")
    other_user = await factory(UserFactory)
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=current_user.id,
        role=MemberRole.ADMIN,
    )
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=other_user.id,
        role=MemberRole.MEMBER,
    )
    await factory(
        InvitationFactory,
        organization_id=org.id,
        email="invited@example.com",
        status=InvitationStatus.PENDING,
    )

    resp = await authenticated_client.get("/orgs/show-co/members")
    assert resp.status_code == 200
    assert other_user.email in resp.text
    assert "invited@example.com" in resp.text


@pytest.mark.asyncio
async def test_invite_member_redirects(authenticated_client, current_user, factory):
    """POST /orgs/{slug}/members/invite creates invitation and redirects."""

    from tests.factories import MembershipFactory, OrganizationFactory

    org = await factory(OrganizationFactory, slug="invite-co")
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=current_user.id,
        role=MemberRole.ADMIN,
    )

    resp = await authenticated_client.post(
        "/orgs/invite-co/members/invite",
        data={"email": "new@example.com", "role": "member"},
    )
    assert resp.status_code in (200, 303)
    if resp.status_code == 303:
        assert "/orgs/invite-co/members" in resp.headers["location"]


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
        role=MemberRole.MEMBER,
    )

    resp = await authenticated_client.post(
        "/orgs/invite403-co/members/invite",
        data={"email": "new@example.com", "role": "member"},
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
        role=MemberRole.ADMIN,
    )
    inv = await factory(
        InvitationFactory,
        organization_id=org.id,
        email="torem@example.com",
        status=InvitationStatus.PENDING,
    )

    resp = await authenticated_client.post(
        f"/orgs/revoke-co/members/invitations/{inv.id}/revoke"
    )
    assert resp.status_code == 303
    assert "/orgs/revoke-co/members" in resp.headers["location"]


@pytest.mark.asyncio
async def test_update_member_role_redirects(
    authenticated_client, current_user, factory
):
    """POST /orgs/{slug}/members/{id}/role updates role and redirects."""
    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory, slug="role-co")
    other = await factory(UserFactory)
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=current_user.id,
        role=MemberRole.ADMIN,
    )
    membership = await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=other.id,
        role=MemberRole.MEMBER,
    )

    resp = await authenticated_client.post(
        f"/orgs/role-co/members/{membership.id}/role",
        data={"role": "admin"},
    )
    assert resp.status_code == 303
    assert "/orgs/role-co/members" in resp.headers["location"]


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
        role=MemberRole.ADMIN,
    )
    membership = await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=other.id,
        role=MemberRole.MEMBER,
    )

    resp = await authenticated_client.post(
        f"/orgs/rem-co/members/{membership.id}/remove"
    )
    assert resp.status_code == 303
    assert "/orgs/rem-co/members" in resp.headers["location"]
