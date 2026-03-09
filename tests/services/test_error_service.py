"""Tests for oopsie.services.error_service."""

import pytest
from oopsie.models.error import Error, ErrorStatus
from oopsie.models.error_occurrence import ErrorOccurrence
from oopsie.services.error_service import upsert_error
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import OrganizationFactory, ProjectFactory


@pytest.mark.asyncio
async def test_upsert_error_creates_new_error(db_session: AsyncSession, factory):
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await upsert_error(
        db_session, project.id, "ValueError", "bad value", "traceback line 1"
    )
    assert error.error_class == "ValueError"
    assert error.message == "bad value"
    assert error.occurrence_count == 1
    assert error.status == ErrorStatus.OPEN
    assert error.project_id == project.id

    result = await db_session.execute(
        select(ErrorOccurrence).where(ErrorOccurrence.error_id == error.id)
    )
    assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_upsert_error_deduplicates_by_fingerprint(
    db_session: AsyncSession, factory
):
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    e1 = await upsert_error(db_session, project.id, "KeyError", "x", "tb")
    e2 = await upsert_error(db_session, project.id, "KeyError", "x", "tb")

    assert e1.id == e2.id
    assert e2.occurrence_count == 2

    result = await db_session.execute(
        select(ErrorOccurrence).where(ErrorOccurrence.error_id == e1.id)
    )
    assert len(result.scalars().all()) == 2


@pytest.mark.asyncio
async def test_upsert_error_without_stack_trace(db_session: AsyncSession, factory):
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await upsert_error(db_session, project.id, "RuntimeError", "oops", None)
    assert error.stack_trace is None
    assert error.occurrence_count == 1


@pytest.mark.asyncio
async def test_upsert_error_different_fingerprints_create_separate_errors(
    db_session: AsyncSession, factory
):
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    e1 = await upsert_error(db_session, project.id, "KeyError", "a", None)
    e2 = await upsert_error(db_session, project.id, "KeyError", "b", None)

    assert e1.id != e2.id

    result = await db_session.execute(
        select(Error).where(Error.project_id == project.id)
    )
    assert len(result.scalars().all()) == 2
