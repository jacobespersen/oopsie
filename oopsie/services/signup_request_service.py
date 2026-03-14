"""Signup request service — create, list, approve, and reject signup requests."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from oopsie.logging import logger
from oopsie.models.org_creation_invitation import OrgCreationInvitation
from oopsie.models.signup_request import SignupRequest, SignupRequestStatus


async def create_signup_request(
    session: AsyncSession,
    *,
    name: str,
    email: str,
    org_name: str,
    reason: str,
) -> SignupRequest:
    """Create a new signup request.

    Raises ValueError if a pending request already exists for this email.
    """
    existing = await session.execute(
        select(SignupRequest).where(
            SignupRequest.email == email,
            SignupRequest.status == SignupRequestStatus.pending,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError("A signup request for this email is already pending review.")

    signup_request = SignupRequest(
        name=name,
        email=email,
        org_name=org_name,
        reason=reason,
    )
    session.add(signup_request)
    await session.flush()
    logger.info(
        "signup_request_created",
        signup_request_id=str(signup_request.id),
        email=email,
    )
    return signup_request


async def list_signup_requests(
    session: AsyncSession,
    *,
    status: SignupRequestStatus | None = None,
) -> list[SignupRequest]:
    """Return signup requests, optionally filtered by status.

    Results are ordered by created_at descending (newest first).
    """
    query = (
        select(SignupRequest)
        .options(joinedload(SignupRequest.reviewed_by))
        .order_by(SignupRequest.created_at.desc())
    )
    if status is not None:
        query = query.where(SignupRequest.status == status)
    result = await session.execute(query)
    return list(result.scalars().unique().all())


async def approve_signup_request(
    session: AsyncSession,
    *,
    signup_request_id: uuid.UUID,
    reviewer_id: uuid.UUID,
) -> SignupRequest:
    """Approve a signup request and create an org-creation invitation.

    Raises LookupError if not found.
    Raises ValueError if not in pending status.
    """
    result = await session.execute(
        select(SignupRequest).where(SignupRequest.id == signup_request_id)
    )
    signup_request = result.scalar_one_or_none()
    if signup_request is None:
        raise LookupError("Signup request not found.")

    if signup_request.status != SignupRequestStatus.pending:
        raise ValueError(f"Signup request is already {signup_request.status.value}.")

    signup_request.status = SignupRequestStatus.approved
    signup_request.reviewed_by_id = reviewer_id
    signup_request.reviewed_at = datetime.now(tz=UTC)

    # Create an org-creation invitation for the approved email
    invitation = OrgCreationInvitation(
        email=signup_request.email,
        org_name=signup_request.org_name,
        signup_request_id=signup_request.id,
        invited_by_id=reviewer_id,
    )
    session.add(invitation)
    await session.flush()

    logger.info(
        "signup_request_approved",
        signup_request_id=str(signup_request.id),
        email=signup_request.email,
        reviewer_id=str(reviewer_id),
    )
    return signup_request


async def reject_signup_request(
    session: AsyncSession,
    *,
    signup_request_id: uuid.UUID,
    reviewer_id: uuid.UUID,
) -> SignupRequest:
    """Reject a signup request.

    Raises LookupError if not found.
    Raises ValueError if not in pending status.
    """
    result = await session.execute(
        select(SignupRequest).where(SignupRequest.id == signup_request_id)
    )
    signup_request = result.scalar_one_or_none()
    if signup_request is None:
        raise LookupError("Signup request not found.")

    if signup_request.status != SignupRequestStatus.pending:
        raise ValueError(f"Signup request is already {signup_request.status.value}.")

    signup_request.status = SignupRequestStatus.rejected
    signup_request.reviewed_by_id = reviewer_id
    signup_request.reviewed_at = datetime.now(tz=UTC)
    await session.flush()

    logger.info(
        "signup_request_rejected",
        signup_request_id=str(signup_request.id),
        email=signup_request.email,
        reviewer_id=str(reviewer_id),
    )
    return signup_request
