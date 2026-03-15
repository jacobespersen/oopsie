"""Tests for the invitation service (create, list, revoke)."""

import uuid

import pytest
from oopsie.models.invitation import Invitation
from oopsie.models.membership import MemberRole
from oopsie.services.invitation_service import (
    create_invitation,
    list_invitations,
    revoke_invitation,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import (
    InvitationFactory,
    MembershipFactory,
    OrganizationFactory,
    OrgCreationInvitationFactory,
    SignupRequestFactory,
    UserFactory,
)


@pytest.mark.asyncio
async def test_create_invitation_creates_pending(db_session: AsyncSession, factory):
    """create_invitation persists an invitation for the given org and email."""
    org = await factory(OrganizationFactory)
    inviter = await factory(UserFactory)

    invitation = await create_invitation(
        db_session,
        organization_id=org.id,
        email="newuser@example.com",
        role=MemberRole.member,
        invited_by_id=inviter.id,
    )

    assert invitation.id is not None
    assert invitation.organization_id == org.id
    assert invitation.email == "newuser@example.com"
    assert invitation.role == MemberRole.member
    assert invitation.invited_by_id == inviter.id


@pytest.mark.asyncio
async def test_create_invitation_updates_existing(db_session: AsyncSession, factory):
    """create_invitation updates role on an existing invite."""
    org = await factory(OrganizationFactory)
    original = await factory(
        InvitationFactory,
        organization_id=org.id,
        email="dup@example.com",
        role=MemberRole.member,
    )

    updated = await create_invitation(
        db_session,
        organization_id=org.id,
        email="dup@example.com",
        role=MemberRole.admin,
        invited_by_id=None,
    )

    assert updated.id == original.id
    assert updated.role == MemberRole.admin


@pytest.mark.asyncio
async def test_create_invitation_raises_for_existing_member(
    db_session: AsyncSession, factory
):
    """create_invitation raises ValueError when email belongs to a user who is
    already a member of any organization (single-org-per-user enforcement)."""
    org = await factory(OrganizationFactory)
    user = await factory(UserFactory, email="member@example.com")
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=user.id,
        role=MemberRole.member,
    )

    with pytest.raises(ValueError, match="already belongs to an organization"):
        await create_invitation(
            db_session,
            organization_id=org.id,
            email="member@example.com",
            role=MemberRole.admin,
            invited_by_id=None,
        )


@pytest.mark.asyncio
async def test_create_invitation_rejects_member_of_other_org(
    db_session: AsyncSession, factory
):
    """create_invitation raises ValueError when email belongs to a user who is
    a member of a different organization."""
    org_a = await factory(OrganizationFactory, slug="org-a")
    org_b = await factory(OrganizationFactory, slug="org-b")
    user = await factory(UserFactory, email="cross-org@example.com")
    await factory(
        MembershipFactory,
        organization_id=org_a.id,
        user_id=user.id,
        role=MemberRole.member,
    )

    with pytest.raises(ValueError, match="already belongs to an organization"):
        await create_invitation(
            db_session,
            organization_id=org_b.id,
            email="cross-org@example.com",
            role=MemberRole.member,
            invited_by_id=None,
        )


@pytest.mark.asyncio
async def test_create_invitation_rejects_pending_invitation_in_other_org(
    db_session: AsyncSession, factory
):
    """create_invitation raises ValueError when email already has a pending
    invitation in a different organization."""
    org_a = await factory(OrganizationFactory, slug="org-a")
    org_b = await factory(OrganizationFactory, slug="org-b")
    await factory(
        InvitationFactory,
        organization_id=org_a.id,
        email="pending@example.com",
    )

    with pytest.raises(ValueError, match="already has a pending invitation"):
        await create_invitation(
            db_session,
            organization_id=org_b.id,
            email="pending@example.com",
            role=MemberRole.member,
            invited_by_id=None,
        )


@pytest.mark.asyncio
async def test_create_invitation_rejects_pending_org_creation_invitation(
    db_session: AsyncSession, factory
):
    """create_invitation raises ValueError when email already has a pending
    OrgCreationInvitation."""
    org = await factory(OrganizationFactory)
    reviewer = await factory(UserFactory)
    signup_request = await factory(SignupRequestFactory, email="orgcreator@example.com")
    await factory(
        OrgCreationInvitationFactory,
        email="orgcreator@example.com",
        org_name="New Org",
        signup_request_id=signup_request.id,
        invited_by_id=reviewer.id,
    )

    with pytest.raises(ValueError, match="already has a pending invitation"):
        await create_invitation(
            db_session,
            organization_id=org.id,
            email="orgcreator@example.com",
            role=MemberRole.member,
            invited_by_id=None,
        )


@pytest.mark.asyncio
async def test_list_invitations_returns_org_invitations(
    db_session: AsyncSession, factory
):
    """list_invitations returns invitations for the org."""
    org = await factory(OrganizationFactory)
    inv = await factory(
        InvitationFactory,
        organization_id=org.id,
        email="pending@example.com",
    )

    results = await list_invitations(db_session, organization_id=org.id)

    assert len(results) == 1
    assert results[0].id == inv.id


@pytest.mark.asyncio
async def test_list_invitations_excludes_other_orgs(db_session: AsyncSession, factory):
    """list_invitations does not return invitations from other organizations."""
    org1 = await factory(OrganizationFactory, slug="org1")
    org2 = await factory(OrganizationFactory, slug="org2")
    await factory(InvitationFactory, organization_id=org1.id, email="a@x.com")
    await factory(InvitationFactory, organization_id=org2.id, email="b@x.com")

    results = await list_invitations(db_session, organization_id=org1.id)

    assert all(inv.organization_id == org1.id for inv in results)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_revoke_invitation_deletes(db_session: AsyncSession, factory):
    """revoke_invitation removes an invitation."""
    org = await factory(OrganizationFactory)
    inv = await factory(
        InvitationFactory,
        organization_id=org.id,
        email="todelete@example.com",
    )

    await revoke_invitation(db_session, invitation_id=inv.id, organization_id=org.id)

    remaining = await db_session.scalar(
        select(Invitation).where(Invitation.id == inv.id)
    )
    assert remaining is None


@pytest.mark.asyncio
async def test_revoke_invitation_raises_when_not_found(
    db_session: AsyncSession, factory
):
    """revoke_invitation raises LookupError when the invitation does not exist."""
    org = await factory(OrganizationFactory)

    with pytest.raises(LookupError):
        await revoke_invitation(
            db_session, invitation_id=uuid.uuid4(), organization_id=org.id
        )


# ---------------------------------------------------------------------------
# Inviter role enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_cannot_invite_with_owner_role(db_session: AsyncSession, factory):
    """ADMIN cannot create an invitation with OWNER role."""
    org = await factory(OrganizationFactory)
    inviter = await factory(UserFactory)

    with pytest.raises(PermissionError, match="higher than your own"):
        await create_invitation(
            db_session,
            organization_id=org.id,
            email="new@example.com",
            role=MemberRole.owner,
            invited_by_id=inviter.id,
            inviter_role=MemberRole.admin,
        )


@pytest.mark.asyncio
async def test_admin_can_invite_with_member_role(db_session: AsyncSession, factory):
    """ADMIN can invite with MEMBER role (below their rank)."""
    org = await factory(OrganizationFactory)
    inviter = await factory(UserFactory)

    invitation = await create_invitation(
        db_session,
        organization_id=org.id,
        email="new@example.com",
        role=MemberRole.member,
        invited_by_id=inviter.id,
        inviter_role=MemberRole.admin,
    )

    assert invitation.role == MemberRole.member


@pytest.mark.asyncio
async def test_admin_can_invite_with_admin_role(db_session: AsyncSession, factory):
    """ADMIN can invite with ADMIN role (equal to their rank)."""
    org = await factory(OrganizationFactory)
    inviter = await factory(UserFactory)

    invitation = await create_invitation(
        db_session,
        organization_id=org.id,
        email="peer@example.com",
        role=MemberRole.admin,
        invited_by_id=inviter.id,
        inviter_role=MemberRole.admin,
    )

    assert invitation.role == MemberRole.admin


@pytest.mark.asyncio
async def test_owner_can_invite_with_owner_role(db_session: AsyncSession, factory):
    """OWNER can invite with OWNER role."""
    org = await factory(OrganizationFactory)
    inviter = await factory(UserFactory)

    invitation = await create_invitation(
        db_session,
        organization_id=org.id,
        email="coowner@example.com",
        role=MemberRole.owner,
        invited_by_id=inviter.id,
        inviter_role=MemberRole.owner,
    )

    assert invitation.role == MemberRole.owner
