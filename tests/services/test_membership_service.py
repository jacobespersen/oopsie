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
    """OWNER can update a MEMBER's role to ADMIN."""
    from oopsie.services.membership_service import update_member_role

    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory)
    user = await factory(UserFactory)
    membership = await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=user.id,
        role=MemberRole.member,
    )

    updated = await update_member_role(
        db_session,
        membership_id=membership.id,
        organization_id=org.id,
        new_role=MemberRole.admin,
        actor_role=MemberRole.owner,
    )

    assert updated.role == MemberRole.admin
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
            new_role=MemberRole.admin,
            actor_role=MemberRole.owner,
        )


@pytest.mark.asyncio
async def test_remove_member_deletes_membership(db_session: AsyncSession, factory):
    """OWNER can remove a MEMBER from the organization."""
    from oopsie.models.membership import Membership
    from oopsie.services.membership_service import remove_member
    from sqlalchemy import select

    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory)
    user = await factory(UserFactory)
    membership = await factory(
        MembershipFactory, organization_id=org.id, user_id=user.id
    )

    await remove_member(
        db_session,
        membership_id=membership.id,
        organization_id=org.id,
        actor_role=MemberRole.owner,
    )

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
            db_session,
            membership_id=uuid.uuid4(),
            organization_id=org.id,
            actor_role=MemberRole.owner,
        )


# ---------------------------------------------------------------------------
# Role hierarchy enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_cannot_promote_member_to_owner(db_session: AsyncSession, factory):
    """ADMIN cannot assign OWNER role — it's equal to or above their rank."""
    from oopsie.services.membership_service import update_member_role

    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory)
    user = await factory(UserFactory)
    membership = await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=user.id,
        role=MemberRole.member,
    )

    with pytest.raises(PermissionError, match="equal to or higher"):
        await update_member_role(
            db_session,
            membership_id=membership.id,
            organization_id=org.id,
            new_role=MemberRole.owner,
            actor_role=MemberRole.admin,
        )


@pytest.mark.asyncio
async def test_admin_cannot_modify_owner(db_session: AsyncSession, factory):
    """ADMIN cannot change an OWNER's role."""
    from oopsie.services.membership_service import update_member_role

    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory)
    owner = await factory(UserFactory)
    membership = await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=owner.id,
        role=MemberRole.owner,
    )

    with pytest.raises(PermissionError, match="equal or higher"):
        await update_member_role(
            db_session,
            membership_id=membership.id,
            organization_id=org.id,
            new_role=MemberRole.member,
            actor_role=MemberRole.admin,
        )


@pytest.mark.asyncio
async def test_admin_cannot_remove_owner(db_session: AsyncSession, factory):
    """ADMIN cannot remove an OWNER."""
    from oopsie.services.membership_service import remove_member

    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory)
    owner = await factory(UserFactory)
    membership = await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=owner.id,
        role=MemberRole.owner,
    )

    with pytest.raises(PermissionError, match="equal or higher"):
        await remove_member(
            db_session,
            membership_id=membership.id,
            organization_id=org.id,
            actor_role=MemberRole.admin,
        )


@pytest.mark.asyncio
async def test_admin_cannot_promote_to_admin(db_session: AsyncSession, factory):
    """ADMIN cannot assign ADMIN role (equal to their own)."""
    from oopsie.services.membership_service import update_member_role

    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory)
    user = await factory(UserFactory)
    membership = await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=user.id,
        role=MemberRole.member,
    )

    with pytest.raises(PermissionError, match="equal to or higher"):
        await update_member_role(
            db_session,
            membership_id=membership.id,
            organization_id=org.id,
            new_role=MemberRole.admin,
            actor_role=MemberRole.admin,
        )


@pytest.mark.asyncio
async def test_owner_can_promote_member_to_admin(db_session: AsyncSession, factory):
    """OWNER can promote a MEMBER to ADMIN."""
    from oopsie.services.membership_service import update_member_role

    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory)
    user = await factory(UserFactory)
    membership = await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=user.id,
        role=MemberRole.member,
    )

    updated = await update_member_role(
        db_session,
        membership_id=membership.id,
        organization_id=org.id,
        new_role=MemberRole.admin,
        actor_role=MemberRole.owner,
    )

    assert updated.role == MemberRole.admin


# ---------------------------------------------------------------------------
# Last-OWNER protection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cannot_demote_last_owner(db_session: AsyncSession, factory):
    """Cannot demote the only OWNER of an organization."""
    from oopsie.services.membership_service import update_member_role

    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory)
    owner = await factory(UserFactory)
    membership = await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=owner.id,
        role=MemberRole.owner,
    )

    with pytest.raises(ValueError, match="last owner"):
        await update_member_role(
            db_session,
            membership_id=membership.id,
            organization_id=org.id,
            new_role=MemberRole.admin,
            actor_role=MemberRole.owner,
        )


@pytest.mark.asyncio
async def test_cannot_remove_last_owner(db_session: AsyncSession, factory):
    """Cannot remove the only OWNER of an organization."""
    from oopsie.services.membership_service import remove_member

    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory)
    owner = await factory(UserFactory)
    membership = await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=owner.id,
        role=MemberRole.owner,
    )

    with pytest.raises(ValueError, match="last owner"):
        await remove_member(
            db_session,
            membership_id=membership.id,
            organization_id=org.id,
            actor_role=MemberRole.owner,
        )


@pytest.mark.asyncio
async def test_can_demote_owner_when_another_exists(db_session: AsyncSession, factory):
    """Can demote an OWNER when at least one other OWNER exists."""
    from oopsie.services.membership_service import update_member_role

    from tests.factories import MembershipFactory, OrganizationFactory, UserFactory

    org = await factory(OrganizationFactory)
    owner1 = await factory(UserFactory)
    owner2 = await factory(UserFactory)
    m1 = await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=owner1.id,
        role=MemberRole.owner,
    )
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=owner2.id,
        role=MemberRole.owner,
    )

    updated = await update_member_role(
        db_session,
        membership_id=m1.id,
        organization_id=org.id,
        new_role=MemberRole.admin,
        actor_role=MemberRole.owner,
    )

    assert updated.role == MemberRole.admin
