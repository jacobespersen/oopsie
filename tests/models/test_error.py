"""Tests for Error model."""

import pytest
from oopsie.models import Error, ErrorStatus, FixAttempt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from tests.factories import ErrorFactory, ProjectFactory


@pytest.mark.asyncio
async def test_error_creation(factory):
    """Error can be created linked to a project with expected defaults."""
    project = await factory(ProjectFactory)
    error = await factory(
        ErrorFactory,
        project_id=project.id,
        error_class="NoMethodError",
        message="undefined method 'foo' for nil:NilClass",
        fingerprint="abc123def456",
    )
    assert error.id is not None
    assert error.project_id == project.id
    assert error.error_class == "NoMethodError"
    assert error.message == "undefined method 'foo' for nil:NilClass"
    assert error.fingerprint == "abc123def456"
    assert error.occurrence_count == 1
    assert error.status == ErrorStatus.OPEN
    assert error.first_seen_at is not None
    assert error.last_seen_at is not None


@pytest.mark.asyncio
async def test_error_unique_fingerprint_per_project(db_session, factory):
    """Duplicate (project_id, fingerprint) raises IntegrityError."""
    project = await factory(ProjectFactory)
    await factory(ErrorFactory, project_id=project.id, fingerprint="abc123def456")

    error2 = ErrorFactory.build(project_id=project.id, fingerprint="abc123def456")
    db_session.add(error2)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_error_different_fingerprint_same_project(db_session, factory):
    """Same project can have multiple errors with different fingerprints."""
    project = await factory(ProjectFactory)
    error1 = await factory(
        ErrorFactory, project_id=project.id, fingerprint="abc123def456"
    )
    error2 = await factory(ErrorFactory, project_id=project.id, fingerprint="xyz789")

    assert error1.id != error2.id
    assert error1.fingerprint != error2.fingerprint


@pytest.mark.asyncio
async def test_error_project_relationship(db_session, factory):
    """Error.project returns the linked Project."""
    project = await factory(ProjectFactory)
    error = await factory(ErrorFactory, project_id=project.id)

    result = await db_session.execute(
        select(Error)
        .where(Error.id == error.id)
        .options(selectinload(Error.project))
    )
    error_loaded = result.scalar_one()
    assert error_loaded.project.id == project.id
    assert error_loaded.project.name == project.name


@pytest.mark.asyncio
async def test_error_fix_attempts_relationship(db_session, factory):
    """Error.fix_attempts returns linked FixAttempt records."""
    project = await factory(ProjectFactory)
    error = await factory(ErrorFactory, project_id=project.id)

    fix_attempt = FixAttempt(error_id=error.id)
    db_session.add(fix_attempt)
    await db_session.flush()

    result = await db_session.execute(
        select(Error)
        .where(Error.id == error.id)
        .options(selectinload(Error.fix_attempts))
    )
    error_loaded = result.scalar_one()
    assert len(error_loaded.fix_attempts) == 1
    assert error_loaded.fix_attempts[0].id == fix_attempt.id


@pytest.mark.asyncio
async def test_cascade_delete_error_deletes_fix_attempts(db_session, factory):
    """Deleting an error deletes its fix_attempts (cascade)."""
    project = await factory(ProjectFactory)
    error = await factory(ErrorFactory, project_id=project.id)

    fix_attempt = FixAttempt(error_id=error.id)
    db_session.add(fix_attempt)
    await db_session.flush()
    fix_attempt_id = fix_attempt.id

    await db_session.delete(error)
    await db_session.flush()

    result = await db_session.execute(
        select(FixAttempt).where(FixAttempt.id == fix_attempt_id)
    )
    assert result.scalar_one_or_none() is None
