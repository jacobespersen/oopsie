"""Tests for signup request service."""

import uuid
from datetime import UTC, datetime

import pytest
from oopsie.exceptions import AlreadyHasOrganizationError
from oopsie.models.membership import MemberRole
from oopsie.models.org_creation_invitation import OrgCreationInvitation
from oopsie.models.signup_request import SignupRequestStatus
from oopsie.services.signup_request_service import (
    approve_signup_request,
    create_signup_request,
    list_signup_requests,
    reject_signup_request,
)
from sqlalchemy import select

from tests.factories import (
    MembershipFactory,
    OrganizationFactory,
    SignupRequestFactory,
    UserFactory,
)

# Reviewed fields required by the CHECK constraint for non-pending requests
_REVIEWED_AT = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.asyncio
async def test_create_signup_request(db_session):
    """create_signup_request persists a new pending request."""
    sr = await create_signup_request(
        db_session,
        name="Alice",
        email="alice@example.com",
        org_name="Alice's Org",
        reason="Testing",
    )
    assert sr.id is not None
    assert sr.status == SignupRequestStatus.pending
    assert sr.email == "alice@example.com"


@pytest.mark.asyncio
async def test_create_duplicate_pending_raises(db_session, factory):
    """create_signup_request raises ValueError for duplicate pending email."""
    await factory(SignupRequestFactory, email="dup@example.com")
    with pytest.raises(ValueError, match="already pending"):
        await create_signup_request(
            db_session,
            name="Bob",
            email="dup@example.com",
            org_name="Bob's Org",
            reason="Testing",
        )


@pytest.mark.asyncio
async def test_create_after_rejection_allowed(db_session, factory):
    """create_signup_request allows resubmission after rejection."""
    reviewer = await factory(UserFactory)
    await factory(
        SignupRequestFactory,
        email="retry@example.com",
        status=SignupRequestStatus.rejected,
        reviewed_by_id=reviewer.id,
        reviewed_at=_REVIEWED_AT,
    )
    sr = await create_signup_request(
        db_session,
        name="Charlie",
        email="retry@example.com",
        org_name="Charlie's Org",
        reason="Trying again",
    )
    assert sr.status == SignupRequestStatus.pending


@pytest.mark.asyncio
async def test_list_signup_requests_filtered(db_session, factory):
    """list_signup_requests filters by status."""
    reviewer = await factory(UserFactory)
    await factory(SignupRequestFactory, status=SignupRequestStatus.pending)
    await factory(
        SignupRequestFactory,
        status=SignupRequestStatus.approved,
        reviewed_by_id=reviewer.id,
        reviewed_at=_REVIEWED_AT,
    )
    await factory(
        SignupRequestFactory,
        status=SignupRequestStatus.rejected,
        reviewed_by_id=reviewer.id,
        reviewed_at=_REVIEWED_AT,
    )

    pending = await list_signup_requests(db_session, status=SignupRequestStatus.pending)
    assert len(pending) == 1


@pytest.mark.asyncio
async def test_list_signup_requests_all(db_session, factory):
    """list_signup_requests returns all when no status filter."""
    reviewer = await factory(UserFactory)
    await factory(SignupRequestFactory, status=SignupRequestStatus.pending)
    await factory(
        SignupRequestFactory,
        status=SignupRequestStatus.approved,
        reviewed_by_id=reviewer.id,
        reviewed_at=_REVIEWED_AT,
    )

    all_requests = await list_signup_requests(db_session)
    assert len(all_requests) == 2


@pytest.mark.asyncio
async def test_list_signup_requests_ordered_newest_first(db_session, factory):
    """list_signup_requests returns newest first (by created_at desc)."""
    earlier = datetime(2026, 1, 1, tzinfo=UTC)
    later = datetime(2026, 1, 2, tzinfo=UTC)

    sr1 = await factory(SignupRequestFactory, name="First", created_at=earlier)
    sr2 = await factory(SignupRequestFactory, name="Second", created_at=later)

    results = await list_signup_requests(db_session)
    assert len(results) == 2
    # sr2 was created after sr1, so it should come first (DESC order)
    assert results[0].id == sr2.id
    assert results[1].id == sr1.id


@pytest.mark.asyncio
async def test_approve_signup_request(db_session, factory):
    """approve_signup_request updates status and creates org-creation invitation."""
    sr = await factory(SignupRequestFactory, email="approve@example.com")
    reviewer = await factory(UserFactory)

    result = await approve_signup_request(
        db_session,
        signup_request_id=sr.id,
        reviewer_id=reviewer.id,
    )
    assert result.status == SignupRequestStatus.approved
    assert result.reviewed_by_id == reviewer.id
    assert result.reviewed_at is not None

    # Verify org-creation invitation was created
    inv_result = await db_session.execute(
        select(OrgCreationInvitation).where(
            OrgCreationInvitation.email == "approve@example.com"
        )
    )
    invitation = inv_result.scalar_one()
    assert invitation.org_name == sr.org_name
    assert invitation.signup_request_id == sr.id
    assert invitation.invited_by_id == reviewer.id


@pytest.mark.asyncio
async def test_approve_not_found_raises(db_session, factory):
    """approve_signup_request raises LookupError for missing request."""
    reviewer = await factory(UserFactory)
    with pytest.raises(LookupError, match="not found"):
        await approve_signup_request(
            db_session,
            signup_request_id=uuid.uuid4(),
            reviewer_id=reviewer.id,
        )


@pytest.mark.asyncio
async def test_approve_already_approved_raises(db_session, factory):
    """approve_signup_request raises ValueError for non-pending request."""
    reviewer = await factory(UserFactory)
    sr = await factory(
        SignupRequestFactory,
        status=SignupRequestStatus.approved,
        reviewed_by_id=reviewer.id,
        reviewed_at=_REVIEWED_AT,
    )
    with pytest.raises(ValueError, match="already approved"):
        await approve_signup_request(
            db_session,
            signup_request_id=sr.id,
            reviewer_id=reviewer.id,
        )


@pytest.mark.asyncio
async def test_reject_signup_request(db_session, factory):
    """reject_signup_request updates status and records reviewer."""
    sr = await factory(SignupRequestFactory)
    reviewer = await factory(UserFactory)

    result = await reject_signup_request(
        db_session,
        signup_request_id=sr.id,
        reviewer_id=reviewer.id,
    )
    assert result.status == SignupRequestStatus.rejected
    assert result.reviewed_by_id == reviewer.id
    assert result.reviewed_at is not None


@pytest.mark.asyncio
async def test_reject_not_found_raises(db_session, factory):
    """reject_signup_request raises LookupError for missing request."""
    reviewer = await factory(UserFactory)
    with pytest.raises(LookupError, match="not found"):
        await reject_signup_request(
            db_session,
            signup_request_id=uuid.uuid4(),
            reviewer_id=reviewer.id,
        )


@pytest.mark.asyncio
async def test_reject_already_rejected_raises(db_session, factory):
    """reject_signup_request raises ValueError for non-pending request."""
    reviewer = await factory(UserFactory)
    sr = await factory(
        SignupRequestFactory,
        status=SignupRequestStatus.rejected,
        reviewed_by_id=reviewer.id,
        reviewed_at=_REVIEWED_AT,
    )
    with pytest.raises(ValueError, match="already rejected"):
        await reject_signup_request(
            db_session,
            signup_request_id=sr.id,
            reviewer_id=reviewer.id,
        )


# ---------------------------------------------------------------------------
# Single-org-per-user enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_signup_request_rejects_existing_member(db_session, factory):
    """create_signup_request raises ValueError when the email belongs to a user
    who already has a membership in any organization."""

    org = await factory(OrganizationFactory)
    user = await factory(UserFactory, email="existing-member@example.com")
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=user.id,
        role=MemberRole.member,
    )

    with pytest.raises(AlreadyHasOrganizationError, match="already belongs"):
        await create_signup_request(
            db_session,
            name="Existing Member",
            email="existing-member@example.com",
            org_name="Another Org",
            reason="Testing",
        )


@pytest.mark.asyncio
async def test_approve_signup_request_rejects_existing_member(db_session, factory):
    """approve_signup_request raises AlreadyHasOrganizationError if the user
    gained a membership between signup request creation and approval."""

    sr = await factory(SignupRequestFactory, email="late-member@example.com")
    reviewer = await factory(UserFactory)

    # Simulate user gaining membership after submitting signup request
    org = await factory(OrganizationFactory)
    user = await factory(UserFactory, email="late-member@example.com")
    await factory(
        MembershipFactory,
        organization_id=org.id,
        user_id=user.id,
        role=MemberRole.member,
    )

    with pytest.raises(AlreadyHasOrganizationError, match="already belongs"):
        await approve_signup_request(
            db_session,
            signup_request_id=sr.id,
            reviewer_id=reviewer.id,
        )
