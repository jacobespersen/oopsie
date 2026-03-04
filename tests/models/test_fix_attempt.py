"""Tests for FixAttempt model."""

import pytest
from oopsie.models import FixAttempt, FixAttemptStatus
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from tests.factories import ErrorFactory, ProjectFactory


@pytest.mark.asyncio
async def test_fix_attempt_creation(db_session, factory):
    """FixAttempt can be created linked to an error with expected defaults."""
    project = await factory(ProjectFactory)
    error = await factory(ErrorFactory, project_id=project.id)

    fix_attempt = FixAttempt(error_id=error.id)
    db_session.add(fix_attempt)
    await db_session.flush()

    assert fix_attempt.id is not None
    assert fix_attempt.error_id == error.id
    assert fix_attempt.status == FixAttemptStatus.PENDING
    assert fix_attempt.branch_name is None
    assert fix_attempt.pr_url is None
    assert fix_attempt.created_at is not None


@pytest.mark.asyncio
async def test_fix_attempt_status_override(db_session, factory):
    """FixAttempt accepts custom status and optional fields."""
    project = await factory(ProjectFactory)
    error = await factory(ErrorFactory, project_id=project.id)

    fix_attempt = FixAttempt(
        error_id=error.id,
        status=FixAttemptStatus.SUCCESS,
        branch_name="oopsie/fix-abc",
        pr_url="https://github.com/org/repo/pull/1",
    )
    db_session.add(fix_attempt)
    await db_session.flush()

    assert fix_attempt.status == FixAttemptStatus.SUCCESS
    assert fix_attempt.branch_name == "oopsie/fix-abc"
    assert fix_attempt.pr_url == "https://github.com/org/repo/pull/1"


@pytest.mark.asyncio
async def test_fix_attempt_error_relationship(db_session, factory):
    """FixAttempt.error returns the linked Error."""
    project = await factory(ProjectFactory)
    error = await factory(ErrorFactory, project_id=project.id)

    fix_attempt = FixAttempt(error_id=error.id)
    db_session.add(fix_attempt)
    await db_session.flush()

    result = await db_session.execute(
        select(FixAttempt)
        .where(FixAttempt.id == fix_attempt.id)
        .options(selectinload(FixAttempt.error))
    )
    fix_attempt_loaded = result.scalar_one()
    assert fix_attempt_loaded.error.id == error.id
    assert fix_attempt_loaded.error.error_class == error.error_class
