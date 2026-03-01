"""Tests for Error model."""

import pytest
from oopsie.models import Error, ErrorStatus, FixAttempt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload


@pytest.mark.asyncio
async def test_error_creation(saved_project, saved_error, sample_error_data):
    """Error can be created linked to a project with expected defaults."""
    assert saved_error.id is not None
    assert saved_error.project_id == saved_project.id
    assert saved_error.error_class == sample_error_data["error_class"]
    assert saved_error.message == sample_error_data["message"]
    assert saved_error.fingerprint == sample_error_data["fingerprint"]
    assert saved_error.occurrence_count == 1
    assert saved_error.status == ErrorStatus.OPEN
    assert saved_error.first_seen_at is not None
    assert saved_error.last_seen_at is not None


@pytest.mark.asyncio
async def test_error_unique_fingerprint_per_project(
    db_session, saved_project, saved_error, sample_error_data
):
    """Duplicate (project_id, fingerprint) raises IntegrityError."""
    error2 = Error(**sample_error_data)
    db_session.add(error2)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_error_different_fingerprint_same_project(
    db_session, saved_project, saved_error, sample_error_data
):
    """Same project can have multiple errors with different fingerprints."""
    error2 = Error(**{**sample_error_data, "fingerprint": "xyz789"})
    db_session.add(error2)
    await db_session.flush()

    assert saved_error.id != error2.id
    assert saved_error.fingerprint != error2.fingerprint


@pytest.mark.asyncio
async def test_error_project_relationship(db_session, saved_project, saved_error):
    """Error.project returns the linked Project."""
    result = await db_session.execute(
        select(Error)
        .where(Error.id == saved_error.id)
        .options(selectinload(Error.project))
    )
    error_loaded = result.scalar_one()
    assert error_loaded.project.id == saved_project.id
    assert error_loaded.project.name == saved_project.name


@pytest.mark.asyncio
async def test_error_fix_attempts_relationship(db_session, saved_error):
    """Error.fix_attempts returns linked FixAttempt records."""
    fix_attempt = FixAttempt(error_id=saved_error.id)
    db_session.add(fix_attempt)
    await db_session.flush()

    result = await db_session.execute(
        select(Error)
        .where(Error.id == saved_error.id)
        .options(selectinload(Error.fix_attempts))
    )
    error_loaded = result.scalar_one()
    assert len(error_loaded.fix_attempts) == 1
    assert error_loaded.fix_attempts[0].id == fix_attempt.id


@pytest.mark.asyncio
async def test_cascade_delete_error_deletes_fix_attempts(db_session, saved_error):
    """Deleting an error deletes its fix_attempts (cascade)."""
    fix_attempt = FixAttempt(error_id=saved_error.id)
    db_session.add(fix_attempt)
    await db_session.flush()
    fix_attempt_id = fix_attempt.id

    await db_session.delete(saved_error)
    await db_session.flush()

    result = await db_session.execute(
        select(FixAttempt).where(FixAttempt.id == fix_attempt_id)
    )
    assert result.scalar_one_or_none() is None
