"""Invitation service — create, list, and revoke org invitations."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.logging import logger
from oopsie.models.invitation import Invitation
from oopsie.models.membership import MemberRole, Membership
from oopsie.models.user import User


async def create_invitation(
    session: AsyncSession,
    organization_id: uuid.UUID,
    email: str,
    role: MemberRole,
    invited_by_id: uuid.UUID | None,
) -> Invitation:
    """Create or update an invitation for an email address.

    If an invitation already exists for this org+email, updates its role.
    Raises ValueError if the email already belongs to an org member.
    """
    # Prevent inviting someone who is already a member
    existing_member = await session.scalar(
        select(Membership)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.organization_id == organization_id,
            User.email == email,
        )
    )
    if existing_member:
        raise ValueError(
            f"{email} is already a member of this organization"
        )

    # Check for an existing invitation — update rather than duplicate
    existing = await session.scalar(
        select(Invitation).where(
            Invitation.organization_id == organization_id,
            Invitation.email == email,
        )
    )
    if existing is not None:
        existing.role = role
        existing.invited_by_id = invited_by_id
        await session.flush()
        logger.info(
            "invitation_updated",
            org_id=str(organization_id),
            email=email,
            role=role.value,
        )
        return existing

    invitation = Invitation(
        organization_id=organization_id,
        email=email,
        role=role,
        invited_by_id=invited_by_id,
    )
    session.add(invitation)
    await session.flush()

    logger.info(
        "invitation_created",
        org_id=str(organization_id),
        email=email,
        role=role.value,
    )
    return invitation


async def list_invitations(
    session: AsyncSession,
    organization_id: uuid.UUID,
) -> list[Invitation]:
    """Return all invitations for the given organization."""
    result = await session.execute(
        select(Invitation).where(
            Invitation.organization_id == organization_id,
        )
    )
    return list(result.scalars().all())


async def revoke_invitation(
    session: AsyncSession,
    invitation_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> None:
    """Delete an invitation.

    Raises LookupError if the invitation does not exist in this org.
    """
    invitation = await session.scalar(
        select(Invitation).where(
            Invitation.id == invitation_id,
            Invitation.organization_id == organization_id,
        )
    )
    if invitation is None:
        raise LookupError(
            f"Invitation {invitation_id} not found in this organization."
        )

    await session.delete(invitation)
    await session.flush()

    logger.info(
        "invitation_revoked",
        invitation_id=str(invitation_id),
        org_id=str(organization_id),
    )
