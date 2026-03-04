"""Tests for ErrorOccurrence model."""

import pytest
from oopsie.models import Error, ErrorOccurrence
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from tests.factories import ErrorFactory, ProjectFactory


@pytest.mark.asyncio
async def test_error_occurrence_creation(db_session, factory):
    """ErrorOccurrence can be created linked to an error."""
    project = await factory(ProjectFactory)
    error = await factory(ErrorFactory, project_id=project.id)

    occurrence = ErrorOccurrence(error_id=error.id)
    db_session.add(occurrence)
    await db_session.flush()

    assert occurrence.id is not None
    assert occurrence.error_id == error.id
    assert occurrence.occurred_at is not None


@pytest.mark.asyncio
async def test_error_occurrences_relationship(db_session, factory):
    """Error.occurrences returns linked ErrorOccurrence records."""
    project = await factory(ProjectFactory)
    error = await factory(ErrorFactory, project_id=project.id)

    for _ in range(3):
        db_session.add(ErrorOccurrence(error_id=error.id))
    await db_session.flush()

    result = await db_session.execute(
        select(Error)
        .where(Error.id == error.id)
        .options(selectinload(Error.occurrences))
    )
    error_loaded = result.scalar_one()
    assert len(error_loaded.occurrences) == 3


@pytest.mark.asyncio
async def test_cascade_delete_error_deletes_occurrences(db_session, factory):
    """Deleting an error deletes its occurrences (cascade)."""
    project = await factory(ProjectFactory)
    error = await factory(ErrorFactory, project_id=project.id)

    occurrence = ErrorOccurrence(error_id=error.id)
    db_session.add(occurrence)
    await db_session.flush()
    occurrence_id = occurrence.id

    await db_session.delete(error)
    await db_session.flush()

    result = await db_session.execute(
        select(ErrorOccurrence).where(ErrorOccurrence.id == occurrence_id)
    )
    assert result.scalar_one_or_none() is None
