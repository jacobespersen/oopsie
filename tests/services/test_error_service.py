"""Tests for oopsie.services.error_service."""

import pytest
from oopsie.models.error import Error, ErrorStatus
from oopsie.models.error_occurrence import ErrorOccurrence
from oopsie.services.error_service import get_errors_for_project, upsert_error
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import ErrorFactory, OrganizationFactory, ProjectFactory


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


@pytest.mark.asyncio
async def test_get_errors_for_project_returns_paginated_results(
    db_session: AsyncSession, factory
):
    """Returns first page of errors ordered by last_seen_at desc."""
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    # Create 3 errors — factory auto-generates unique fingerprints
    for _ in range(3):
        await factory(ErrorFactory, project_id=project.id)

    errors, total_count = await get_errors_for_project(
        db_session, project.id, page=1, per_page=2
    )

    assert total_count == 3
    assert len(errors) == 2


@pytest.mark.asyncio
async def test_get_errors_for_project_second_page(db_session: AsyncSession, factory):
    """Second page returns remaining errors."""
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    for _ in range(3):
        await factory(ErrorFactory, project_id=project.id)

    errors, total_count = await get_errors_for_project(
        db_session, project.id, page=2, per_page=2
    )

    assert total_count == 3
    assert len(errors) == 1


@pytest.mark.asyncio
async def test_get_errors_for_project_empty(db_session: AsyncSession, factory):
    """Returns empty list and 0 count when no errors exist."""
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)

    errors, total_count = await get_errors_for_project(
        db_session, project.id, page=1, per_page=25
    )

    assert total_count == 0
    assert len(errors) == 0


@pytest.mark.asyncio
async def test_get_errors_for_project_ordered_by_last_seen(
    db_session: AsyncSession, factory
):
    """Results are ordered by last_seen_at descending."""
    from datetime import UTC, datetime, timedelta

    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    now = datetime.now(UTC)
    old = await factory(
        ErrorFactory, project_id=project.id, last_seen_at=now - timedelta(hours=2)
    )
    new = await factory(ErrorFactory, project_id=project.id, last_seen_at=now)

    errors, _ = await get_errors_for_project(
        db_session, project.id, page=1, per_page=25
    )

    assert errors[0].id == new.id
    assert errors[1].id == old.id


@pytest.mark.asyncio
async def test_get_errors_for_project_scoped_to_project(
    db_session: AsyncSession, factory
):
    """Only returns errors for the specified project."""
    org = await factory(OrganizationFactory)
    project_a = await factory(ProjectFactory, organization_id=org.id)
    project_b = await factory(ProjectFactory, organization_id=org.id)
    await factory(ErrorFactory, project_id=project_a.id)
    await factory(ErrorFactory, project_id=project_b.id)

    errors, total_count = await get_errors_for_project(
        db_session, project_a.id, page=1, per_page=25
    )

    assert total_count == 1
    assert len(errors) == 1
    assert errors[0].project_id == project_a.id


@pytest.mark.asyncio
async def test_upsert_error_stores_exception_chain(db_session: AsyncSession, factory):
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    chain = [
        {"type": "ActiveRecord::RecordNotFound", "value": "Not found"},
        {"type": "AuthError", "value": "Login failed"},
    ]
    error = await upsert_error(
        session=db_session,
        project_id=project.id,
        error_class="AuthError",
        message="Login failed",
        stack_trace="tb",
        exception_chain=chain,
    )
    result = await db_session.execute(
        select(ErrorOccurrence).where(ErrorOccurrence.error_id == error.id)
    )
    occurrence = result.scalar_one()
    assert occurrence.exception_chain == chain


@pytest.mark.asyncio
async def test_upsert_error_stores_execution_context(db_session: AsyncSession, factory):
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    ctx = {"type": "http", "description": "POST /api/users", "data": {"method": "POST"}}
    error = await upsert_error(
        session=db_session,
        project_id=project.id,
        error_class="ValueError",
        message="bad",
        stack_trace=None,
        execution_context=ctx,
    )
    result = await db_session.execute(
        select(ErrorOccurrence).where(ErrorOccurrence.error_id == error.id)
    )
    occurrence = result.scalar_one()
    assert occurrence.execution_context == ctx


@pytest.mark.asyncio
async def test_upsert_error_context_fields_default_to_none(
    db_session: AsyncSession, factory
):
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await upsert_error(
        session=db_session,
        project_id=project.id,
        error_class="E",
        message="m",
        stack_trace=None,
    )
    result = await db_session.execute(
        select(ErrorOccurrence).where(ErrorOccurrence.error_id == error.id)
    )
    occurrence = result.scalar_one()
    assert occurrence.exception_chain is None
    assert occurrence.execution_context is None
