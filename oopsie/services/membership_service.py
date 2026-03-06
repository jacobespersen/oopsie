"""Membership service — list, update roles, and remove org members."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from oopsie.logging import logger
from oopsie.models.membership import MemberRole, Membership


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


async def update_member_role(
    session: AsyncSession,
    membership_id: uuid.UUID,
    organization_id: uuid.UUID,
    new_role: MemberRole,
) -> Membership:
    """Update the role of an existing membership.

    Raises LookupError if the membership does not exist in the organization.
    """
    membership = await session.scalar(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.organization_id == organization_id,
        )
    )
    if membership is None:
        raise LookupError(f"Membership {membership_id} not found in this organization.")

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
) -> None:
    """Remove a membership from the organization.

    Raises LookupError if the membership does not exist in the organization.
    """
    membership = await session.scalar(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.organization_id == organization_id,
        )
    )
    if membership is None:
        raise LookupError(f"Membership {membership_id} not found in this organization.")

    await session.delete(membership)
    await session.flush()

    logger.info(
        "membership_removed",
        membership_id=str(membership_id),
        org_id=str(organization_id),
    )
