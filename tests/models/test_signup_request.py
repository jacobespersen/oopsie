"""Tests for SignupRequest and OrgCreationInvitation models."""

from datetime import UTC, datetime

import pytest
from oopsie.models.org_creation_invitation import OrgCreationInvitation
from oopsie.models.signup_request import SignupRequest, SignupRequestStatus
from sqlalchemy import select
from tests.factories import (
    OrgCreationInvitationFactory,
    SignupRequestFactory,
    UserFactory,
)

# Reviewed fields required by the CHECK constraint for non-pending requests
_REVIEWED_AT = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.asyncio
async def test_signup_request_creation(db_session, factory):
    """SignupRequest can be created with all fields."""
    sr = await factory(SignupRequestFactory)
    assert sr.id is not None
    assert sr.status == SignupRequestStatus.pending
    assert sr.reviewed_by_id is None
    assert sr.reviewed_at is None
    assert sr.created_at is not None


@pytest.mark.asyncio
async def test_signup_request_default_status(db_session, factory):
    """SignupRequest defaults to pending status."""
    sr = await factory(SignupRequestFactory)
    assert sr.status == SignupRequestStatus.pending


@pytest.mark.asyncio
async def test_signup_request_reviewed_by_relationship(db_session, factory):
    """SignupRequest.reviewed_by resolves to User."""
    reviewer = await factory(UserFactory)
    sr = await factory(
        SignupRequestFactory,
        reviewed_by_id=reviewer.id,
        reviewed_at=_REVIEWED_AT,
        status=SignupRequestStatus.approved,
    )
    result = await db_session.execute(
        select(SignupRequest).where(SignupRequest.id == sr.id)
    )
    loaded = result.scalar_one()
    await db_session.refresh(loaded, ["reviewed_by"])
    assert loaded.reviewed_by.id == reviewer.id


@pytest.mark.asyncio
async def test_org_creation_invitation_creation(db_session, factory):
    """OrgCreationInvitation can be created with required FKs."""
    admin = await factory(UserFactory)
    sr = await factory(SignupRequestFactory)
    invitation = await factory(
        OrgCreationInvitationFactory,
        email="test@example.com",
        org_name="Test Org",
        signup_request_id=sr.id,
        invited_by_id=admin.id,
    )
    assert invitation.id is not None
    assert invitation.email == "test@example.com"
    assert invitation.created_at is not None


@pytest.mark.asyncio
async def test_org_creation_invitation_relationships(db_session, factory):
    """OrgCreationInvitation resolves signup_request and invited_by."""
    admin = await factory(UserFactory)
    sr = await factory(SignupRequestFactory)
    invitation = await factory(
        OrgCreationInvitationFactory,
        signup_request_id=sr.id,
        invited_by_id=admin.id,
    )
    result = await db_session.execute(
        select(OrgCreationInvitation).where(OrgCreationInvitation.id == invitation.id)
    )
    loaded = result.scalar_one()
    await db_session.refresh(loaded, ["signup_request", "invited_by"])
    assert loaded.signup_request.id == sr.id
    assert loaded.invited_by.id == admin.id


@pytest.mark.asyncio
async def test_partial_unique_index_allows_rejected_resubmission(db_session, factory):
    """After rejection, a new pending request for the same email is allowed."""
    email = "resubmit@example.com"
    reviewer = await factory(UserFactory)
    await factory(
        SignupRequestFactory,
        email=email,
        status=SignupRequestStatus.rejected,
        reviewed_by_id=reviewer.id,
        reviewed_at=_REVIEWED_AT,
    )
    # Should not raise — partial unique index only covers pending
    sr2 = await factory(SignupRequestFactory, email=email)
    assert sr2.status == SignupRequestStatus.pending
