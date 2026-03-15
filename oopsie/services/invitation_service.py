"""Invitation service — create, list, and revoke org invitations."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.logging import logger
from oopsie.models.invitation import Invitation
from oopsie.models.membership import MemberRole, role_rank
from oopsie.models.org_creation_invitation import OrgCreationInvitation
from oopsie.services.membership_service import has_membership_by_email


async def create_invitation(
    session: AsyncSession,
    organization_id: uuid.UUID,
    email: str,
    role: MemberRole,
    invited_by_id: uuid.UUID | None,
    inviter_role: MemberRole | None = None,
) -> Invitation:
    """Create or update an invitation for an email address.

    If an invitation already exists for this org+email, updates its role.
    Raises ValueError if the email already belongs to an org member (any org),
    or if the user already has a pending invitation of any type.
    Raises PermissionError if the inviter tries to grant a role above their own.
    """
    # Enforce: inviter can only grant roles at or below their own rank
    if inviter_role is not None and role_rank(role) > role_rank(inviter_role):
        raise PermissionError("Cannot invite with a role higher than your own.")

    # Single-org enforcement: reject if user already belongs to any organization
    if await has_membership_by_email(session, email):
        raise ValueError(f"{email} already belongs to an organization")

    # Single-org enforcement: reject if user has a pending invitation elsewhere
    existing_other_invitation = await session.scalar(
        select(Invitation).where(
            Invitation.email == email,
            Invitation.organization_id != organization_id,
        )
    )
    if existing_other_invitation:
        raise ValueError(f"{email} already has a pending invitation")

    # Single-org enforcement: reject if user has a pending org-creation invitation
    existing_org_creation = await session.scalar(
        select(OrgCreationInvitation).where(OrgCreationInvitation.email == email)
    )
    if existing_org_creation:
        raise ValueError(f"{email} already has a pending invitation")

    # Check for an existing invitation in this org — update rather than duplicate
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
        raise LookupError(f"Invitation {invitation_id} not found in this organization.")

    await session.delete(invitation)
    await session.flush()

    logger.info(
        "invitation_revoked",
        invitation_id=str(invitation_id),
        org_id=str(organization_id),
    )
