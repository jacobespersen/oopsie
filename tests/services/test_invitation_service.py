"""Tests for the invitation service (create, list, revoke)."""

import pytest
from oopsie.models.membership import MemberRole
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_create_invitation_creates_pending(db_session: AsyncSession, factory):
    """create_invitation persists an invitation for the given org and email."""
    from oopsie.services.invitation_service import create_invitation

    from tests.factories import OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory)
    inviter = await factory(UserFactory)

    invitation = await create_invitation(
        db_session,
        organization_id=org.id,
        email="newuser@example.com",
        role=MemberRole.MEMBER,
        invited_by_id=inviter.id,
    )

    assert invitation.id is not None
    assert invitation.organization_id == org.id
    assert invitation.email == "newuser@example.com"
    assert invitation.role == MemberRole.MEMBER
    assert invitation.invited_by_id == inviter.id


@pytest.mark.asyncio
async def test_create_invitation_updates_existing(db_session: AsyncSession, factory):
    """create_invitation updates role on an existing invite."""
    from oopsie.services.invitation_service import create_invitation

    from tests.factories import InvitationFactory, OrganizationFactory

    org = await factory(OrganizationFactory)
    original = await factory(
        InvitationFactory,
        organization_id=org.id,
        email="dup@example.com",
        role=MemberRole.MEMBER,
    )

    updated = await create_invitation(
        db_session,
        organization_id=org.id,
        email="dup@example.com",
        role=MemberRole.ADMIN,
        invited_by_id=None,
    )

    assert updated.id == original.id
    assert updated.role == MemberRole.ADMIN


@pytest.mark.asyncio
async def test_create_invitation_raises_for_existing_member(
    db_session: AsyncSession, factory
):
    """create_invitation raises ValueError when email is already an org member."""
    from oopsie.services.invitation_service import create_invitation

    from tests.factories import (
        MembershipFactory,
        OrganizationFactory,
        UserFactory,
    )

    org = await factory(OrganizationFactory)
    user = await factory(UserFactory, email="member@example.com")
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=user.id,
        role=MemberRole.MEMBER,
    )

    with pytest.raises(ValueError, match="already a member"):
        await create_invitation(
            db_session,
            organization_id=org.id,
            email="member@example.com",
            role=MemberRole.ADMIN,
            invited_by_id=None,
        )


@pytest.mark.asyncio
async def test_list_invitations_returns_org_invitations(
    db_session: AsyncSession, factory
):
    """list_invitations returns invitations for the org."""
    from oopsie.services.invitation_service import list_invitations

    from tests.factories import InvitationFactory, OrganizationFactory

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
    from oopsie.services.invitation_service import list_invitations

    from tests.factories import InvitationFactory, OrganizationFactory

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
    from oopsie.models.invitation import Invitation
    from oopsie.services.invitation_service import revoke_invitation
    from sqlalchemy import select

    from tests.factories import InvitationFactory, OrganizationFactory

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
    import uuid

    from oopsie.services.invitation_service import revoke_invitation

    from tests.factories import OrganizationFactory

    org = await factory(OrganizationFactory)

    with pytest.raises(LookupError):
        await revoke_invitation(
            db_session, invitation_id=uuid.uuid4(), organization_id=org.id
        )
