"""Invitation model tests."""

import pytest
from oopsie.models.invitation import Invitation, InvitationStatus
from oopsie.models.membership import MemberRole
from oopsie.models.organization import Organization
from oopsie.models.user import User
from sqlalchemy.exc import IntegrityError


@pytest.mark.asyncio
async def test_invitation_creation(db_session):
    """Invitation can be created for an email with a role."""
    org = Organization(name="Acme", slug="acme")
    db_session.add(org)
    await db_session.flush()

    inv = Invitation(
        organization_id=org.id,
        email="bob@example.com",
        role=MemberRole.MEMBER,
    )
    db_session.add(inv)
    await db_session.flush()

    assert inv.id is not None
    assert inv.email == "bob@example.com"
    assert inv.role == MemberRole.MEMBER
    assert inv.status == InvitationStatus.PENDING
    assert inv.invited_by_id is None
    assert inv.created_at is not None


@pytest.mark.asyncio
async def test_invitation_with_inviter(db_session):
    """Invitation can reference the user who sent it."""
    org = Organization(name="Acme", slug="acme")
    inviter = User(email="alice@example.com", name="Alice", google_sub="g-1")
    db_session.add(org)
    db_session.add(inviter)
    await db_session.flush()

    inv = Invitation(
        organization_id=org.id,
        email="bob@example.com",
        role=MemberRole.ADMIN,
        invited_by_id=inviter.id,
    )
    db_session.add(inv)
    await db_session.flush()

    assert inv.invited_by_id == inviter.id


@pytest.mark.asyncio
async def test_invitation_unique_pending_per_org_email(db_session):
    """Cannot have two PENDING invitations for the same email in the same org."""
    org = Organization(name="Acme", slug="acme")
    db_session.add(org)
    await db_session.flush()

    db_session.add(
        Invitation(organization_id=org.id, email="bob@example.com", role=MemberRole.MEMBER)
    )
    await db_session.flush()

    db_session.add(
        Invitation(organization_id=org.id, email="bob@example.com", role=MemberRole.ADMIN)
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_invitation_status_values(db_session):
    """InvitationStatus enum has expected values."""
    assert InvitationStatus.PENDING.value == "pending"
    assert InvitationStatus.ACCEPTED.value == "accepted"
