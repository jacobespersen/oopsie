"""Tests for pipeline context loading."""

import pytest
from oopsie.models.error_occurrence import ErrorOccurrence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import (
    ErrorFactory,
    ErrorOccurrenceFactory,
    OrganizationFactory,
    ProjectFactory,
)


@pytest.mark.asyncio
async def test_latest_occurrence_context_is_retrievable(
    db_session: AsyncSession, factory
):
    """Latest occurrence JSONB context is fetchable by the pipeline query."""
    from oopsie.models.error import ErrorStatus

    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id, status=ErrorStatus.OPEN)

    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)

    # Create two occurrences with explicit timestamps to ensure deterministic ordering
    await factory(
        ErrorOccurrenceFactory,
        error_id=error.id,
        occurred_at=now - timedelta(minutes=5),
    )
    chain = [{"type": "E", "value": "v"}]
    ctx = {"type": "http", "description": "GET /health"}
    await factory(
        ErrorOccurrenceFactory,
        error_id=error.id,
        occurred_at=now,
        exception_chain=chain,
        execution_context=ctx,
    )

    # Replicate the query pattern used in _load_and_prepare
    result = await db_session.execute(
        select(ErrorOccurrence)
        .where(ErrorOccurrence.error_id == error.id)
        .order_by(ErrorOccurrence.occurred_at.desc())
        .limit(1)
    )
    latest_occurrence = result.scalar_one()
    assert latest_occurrence.exception_chain == chain
    assert latest_occurrence.execution_context == ctx


@pytest.mark.asyncio
async def test_occurrence_context_none_when_not_provided(
    db_session: AsyncSession, factory
):
    """Occurrences without context return None for JSONB fields."""
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    await factory(ErrorOccurrenceFactory, error_id=error.id)

    result = await db_session.execute(
        select(ErrorOccurrence).where(ErrorOccurrence.error_id == error.id)
    )
    occurrence = result.scalar_one()
    assert occurrence.exception_chain is None
    assert occurrence.execution_context is None
