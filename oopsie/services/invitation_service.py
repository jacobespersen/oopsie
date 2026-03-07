"""Invitation service — create, list, and revoke org invitations."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.logging import logger
from oopsie.models.invitation import Invitation, InvitationStatus
from oopsie.models.membership import MemberRole


async def create_invitation(
    session: AsyncSession,
    organization_id: uuid.UUID,
    email: str,
    role: MemberRole,
    invited_by_id: uuid.UUID | None,
) -> Invitation:
    """Create or re-activate an invitation for an email address.

    If a PENDING invitation already exists, updates its role.
    Raises ValueError if the email has already accepted.
    """
    # Check for an existing invitation for this org+email.
    # If found, update it rather than creating a duplicate.
    existing = await session.scalar(
        select(Invitation).where(
            Invitation.organization_id == organization_id,
            Invitation.email == email,
        )
    )
    if existing is not None:
        if existing.status == InvitationStatus.ACCEPTED:
            raise ValueError(
                f"{email} already accepted an invitation"
            )
        # Re-invite: update role and inviter on the existing PENDING row
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
        status=InvitationStatus.PENDING,
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
    """Return all pending invitations for the given organization."""
    result = await session.execute(
        select(Invitation).where(
            Invitation.organization_id == organization_id,
            Invitation.status == InvitationStatus.PENDING,
        )
    )
    return list(result.scalars().all())


async def revoke_invitation(
    session: AsyncSession,
    invitation_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> None:
    """Delete a pending invitation.

    Raises LookupError if the invitation does not exist or is not pending.
    """
    invitation = await session.scalar(
        select(Invitation).where(
            Invitation.id == invitation_id,
            Invitation.organization_id == organization_id,
            Invitation.status == InvitationStatus.PENDING,
        )
    )
    if invitation is None:
        raise LookupError(
            f"Pending invitation {invitation_id} not found in this organization."
        )

    await session.delete(invitation)
    await session.flush()

    logger.info(
        "invitation_revoked",
        invitation_id=str(invitation_id),
        org_id=str(organization_id),
    )
