"""Tests for the membership service (list, update role, remove)."""

import pytest
from oopsie.models.membership import MemberRole
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_list_members_returns_all_for_org(db_session: AsyncSession, factory):
    """list_members returns all memberships for the given org."""
    from oopsie.services.membership_service import list_members

    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory)
    user1 = await factory(UserFactory)
    user2 = await factory(UserFactory)
    await factory(MembershipFactory, organization_id=org.id, user_id=user1.id)
    await factory(MembershipFactory, organization_id=org.id, user_id=user2.id)

    results = await list_members(db_session, organization_id=org.id)

    assert len(results) == 2
    user_ids = {m.user_id for m in results}
    assert user_ids == {user1.id, user2.id}


@pytest.mark.asyncio
async def test_list_members_excludes_other_orgs(db_session: AsyncSession, factory):
    """list_members does not return memberships from other organizations."""
    from oopsie.services.membership_service import list_members

    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org1 = await factory(OrganizationFactory, slug="org1")
    org2 = await factory(OrganizationFactory, slug="org2")
    user = await factory(UserFactory)
    await factory(MembershipFactory, organization_id=org1.id, user_id=user.id)

    results = await list_members(db_session, organization_id=org2.id)

    assert results == []


@pytest.mark.asyncio
async def test_update_member_role_changes_role(db_session: AsyncSession, factory):
    """update_member_role updates the role of an existing membership."""
    from oopsie.services.membership_service import update_member_role

    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory)
    user = await factory(UserFactory)
    membership = await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=user.id,
        role=MemberRole.MEMBER,
    )

    updated = await update_member_role(
        db_session,
        membership_id=membership.id,
        organization_id=org.id,
        new_role=MemberRole.ADMIN,
    )

    assert updated.role == MemberRole.ADMIN
    assert updated.id == membership.id


@pytest.mark.asyncio
async def test_update_member_role_raises_when_not_found(
    db_session: AsyncSession, factory
):
    """update_member_role raises LookupError when membership does not exist."""
    import uuid

    from oopsie.services.membership_service import update_member_role

    from tests.factories import OrganizationFactory

    org = await factory(OrganizationFactory)

    with pytest.raises(LookupError):
        await update_member_role(
            db_session,
            membership_id=uuid.uuid4(),
            organization_id=org.id,
            new_role=MemberRole.ADMIN,
        )


@pytest.mark.asyncio
async def test_remove_member_deletes_membership(db_session: AsyncSession, factory):
    """remove_member deletes the membership from the database."""
    from oopsie.models.membership import Membership
    from oopsie.services.membership_service import remove_member
    from sqlalchemy import select

    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory)
    user = await factory(UserFactory)
    membership = await factory(
        MembershipFactory, organization_id=org.id, user_id=user.id
    )

    await remove_member(db_session, membership_id=membership.id, organization_id=org.id)

    remaining = await db_session.scalar(
        select(Membership).where(Membership.id == membership.id)
    )
    assert remaining is None


@pytest.mark.asyncio
async def test_remove_member_raises_when_not_found(db_session: AsyncSession, factory):
    """remove_member raises LookupError when membership does not exist."""
    import uuid

    from oopsie.services.membership_service import remove_member

    from tests.factories import OrganizationFactory

    org = await factory(OrganizationFactory)

    with pytest.raises(LookupError):
        await remove_member(
            db_session, membership_id=uuid.uuid4(), organization_id=org.id
        )
