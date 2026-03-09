"""Membership service — list, update roles, and remove org members."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from oopsie.logging import logger
from oopsie.models.membership import MemberRole, Membership, role_rank


async def list_members(
    session: AsyncSession,
    organization_id: uuid.UUID,
) -> list[Membership]:
    """Return all memberships for the given organization, with user eagerly loaded."""
    result = await session.execute(
        select(Membership)
        .where(Membership.organization_id == organization_id)
        .options(selectinload(Membership.user))
    )
    return list(result.scalars().all())


async def _count_owners(session: AsyncSession, organization_id: uuid.UUID) -> int:
    """Return the number of OWNERs in an organization."""
    result = await session.scalar(
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.organization_id == organization_id,
            Membership.role == MemberRole.owner,
        )
    )
    return result or 0


async def update_member_role(
    session: AsyncSession,
    membership_id: uuid.UUID,
    organization_id: uuid.UUID,
    new_role: MemberRole,
    actor_role: MemberRole,
) -> Membership:
    """Update the role of an existing membership.

    Raises LookupError if the membership does not exist in the organization.
    Raises PermissionError if the actor lacks sufficient privileges.
    Raises ValueError if the operation would remove the last OWNER.
    """
    membership = await session.scalar(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.organization_id == organization_id,
        )
    )
    if membership is None:
        raise LookupError(f"Membership {membership_id} not found in this organization.")

    # OWNERs can modify anyone and assign any role.
    # Non-OWNERs must outrank both the target and the new role.
    actor_rank = role_rank(actor_role)
    if actor_role != MemberRole.owner:
        if actor_rank <= role_rank(membership.role):
            raise PermissionError(
                "Cannot modify a member with an equal or higher role."
            )
        if actor_rank <= role_rank(new_role):
            raise PermissionError(
                "Cannot assign a role equal to or higher than your own."
            )

    # Prevent removing the last OWNER
    if membership.role == MemberRole.owner and new_role != MemberRole.owner:
        owner_count = await _count_owners(session, organization_id)
        if owner_count <= 1:
            raise ValueError("Cannot demote the last owner of the organization.")

    old_role = membership.role
    membership.role = new_role
    await session.flush()

    logger.info(
        "membership_role_updated",
        membership_id=str(membership_id),
        org_id=str(organization_id),
        old_role=old_role.value,
        new_role=new_role.value,
    )
    return membership


async def remove_member(
    session: AsyncSession,
    membership_id: uuid.UUID,
    organization_id: uuid.UUID,
    actor_role: MemberRole,
) -> None:
    """Remove a membership from the organization.

    Raises LookupError if the membership does not exist in the organization.
    Raises PermissionError if the actor lacks sufficient privileges.
    Raises ValueError if the operation would remove the last OWNER.
    """
    membership = await session.scalar(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.organization_id == organization_id,
        )
    )
    if membership is None:
        raise LookupError(f"Membership {membership_id} not found in this organization.")

    # OWNERs can remove anyone; non-OWNERs must outrank the target
    if actor_role != MemberRole.owner:
        if role_rank(actor_role) <= role_rank(membership.role):
            raise PermissionError(
                "Cannot remove a member with an equal or higher role."
            )

    # Prevent removing the last OWNER
    if membership.role == MemberRole.owner:
        owner_count = await _count_owners(session, organization_id)
        if owner_count <= 1:
            raise ValueError("Cannot remove the last owner of the organization.")

    await session.delete(membership)
    await session.flush()

    logger.info(
        "membership_removed",
        membership_id=str(membership_id),
        org_id=str(organization_id),
    )
