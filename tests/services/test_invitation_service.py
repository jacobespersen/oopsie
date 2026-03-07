"""Tests for the invitation service (create, list, revoke)."""

import pytest
from oopsie.models.invitation import InvitationStatus
from oopsie.models.membership import MemberRole
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_create_invitation_creates_pending(db_session: AsyncSession, factory):
    """create_invitation persists a pending invitation for the given org and email."""
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
    assert invitation.status == InvitationStatus.PENDING
    assert invitation.invited_by_id == inviter.id


@pytest.mark.asyncio
async def test_create_invitation_updates_existing_pending(
    db_session: AsyncSession, factory
):
    """create_invitation updates role on an existing PENDING invite."""
    from oopsie.services.invitation_service import create_invitation

    from tests.factories import InvitationFactory, OrganizationFactory

    org = await factory(OrganizationFactory)
    original = await factory(
        InvitationFactory,
        organization_id=org.id,
        email="dup@example.com",
        role=MemberRole.MEMBER,
        status=InvitationStatus.PENDING,
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
    assert updated.status == InvitationStatus.PENDING


@pytest.mark.asyncio
async def test_create_invitation_raises_on_accepted(
    db_session: AsyncSession, factory
):
    """create_invitation raises ValueError when email already accepted."""
    from oopsie.services.invitation_service import create_invitation

    from tests.factories import InvitationFactory, OrganizationFactory

    org = await factory(OrganizationFactory)
    await factory(
        InvitationFactory,
        organization_id=org.id,
        email="prev@example.com",
        status=InvitationStatus.ACCEPTED,
    )

    with pytest.raises(ValueError, match="already accepted"):
        await create_invitation(
            db_session,
            organization_id=org.id,
            email="prev@example.com",
            role=MemberRole.MEMBER,
            invited_by_id=None,
        )


@pytest.mark.asyncio
async def test_list_invitations_returns_pending_only(
    db_session: AsyncSession, factory
):
    """list_invitations returns only PENDING invitations for the org."""
    from oopsie.services.invitation_service import list_invitations

    from tests.factories import InvitationFactory, OrganizationFactory

    org = await factory(OrganizationFactory)
    pending = await factory(
        InvitationFactory,
        organization_id=org.id,
        email="pending@example.com",
        status=InvitationStatus.PENDING,
    )
    # Different email — unique constraint is on (org, email)
    await factory(
        InvitationFactory,
        organization_id=org.id,
        email="already-accepted@example.com",
        status=InvitationStatus.ACCEPTED,
    )

    results = await list_invitations(db_session, organization_id=org.id)

    assert len(results) == 1
    assert results[0].id == pending.id


@pytest.mark.asyncio
async def test_list_invitations_excludes_other_orgs(
    db_session: AsyncSession, factory
):
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
async def test_revoke_invitation_deletes_pending(db_session: AsyncSession, factory):
    """revoke_invitation removes a pending invitation."""
    from oopsie.models.invitation import Invitation
    from oopsie.services.invitation_service import revoke_invitation
    from sqlalchemy import select

    from tests.factories import InvitationFactory, OrganizationFactory

    org = await factory(OrganizationFactory)
    inv = await factory(
        InvitationFactory,
        organization_id=org.id,
        email="todelete@example.com",
        status=InvitationStatus.PENDING,
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


@pytest.mark.asyncio
async def test_revoke_invitation_raises_for_accepted(
    db_session: AsyncSession, factory
):
    """revoke_invitation raises LookupError for an already-accepted invitation."""
    from oopsie.services.invitation_service import revoke_invitation

    from tests.factories import InvitationFactory, OrganizationFactory

    org = await factory(OrganizationFactory)
    inv = await factory(
        InvitationFactory,
        organization_id=org.id,
        email="done@example.com",
        status=InvitationStatus.ACCEPTED,
    )

    with pytest.raises(LookupError):
        await revoke_invitation(
            db_session, invitation_id=inv.id, organization_id=org.id
        )
