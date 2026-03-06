"""Membership model tests."""

import pytest
from oopsie.models.membership import MemberRole, Membership
from oopsie.models.organization import Organization
from oopsie.models.user import User
from sqlalchemy.exc import IntegrityError


@pytest.mark.asyncio
async def test_membership_creation(db_session):
    """Membership links a user to an organization with a role."""
    org = Organization(name="Acme", slug="acme")
    user = User(email="alice@example.com", name="Alice", google_sub="google-1")
    db_session.add(org)
    db_session.add(user)
    await db_session.flush()

    membership = Membership(organization_id=org.id, user_id=user.id, role=MemberRole.MEMBER)
    db_session.add(membership)
    await db_session.flush()

    assert membership.id is not None
    assert membership.organization_id == org.id
    assert membership.user_id == user.id
    assert membership.role == MemberRole.MEMBER
    assert membership.created_at is not None


@pytest.mark.asyncio
async def test_membership_unique_per_org(db_session):
    """A user can only have one membership per organization."""
    org = Organization(name="Acme", slug="acme")
    user = User(email="alice@example.com", name="Alice", google_sub="google-1")
    db_session.add(org)
    db_session.add(user)
    await db_session.flush()

    db_session.add(Membership(organization_id=org.id, user_id=user.id, role=MemberRole.MEMBER))
    await db_session.flush()

    db_session.add(Membership(organization_id=org.id, user_id=user.id, role=MemberRole.ADMIN))
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_member_role_values(db_session):
    """MemberRole enum has the expected values."""
    assert MemberRole.OWNER.value == "owner"
    assert MemberRole.ADMIN.value == "admin"
    assert MemberRole.MEMBER.value == "member"
