"""Tests for oopsie.services.fix_service."""

import uuid

import pytest
from oopsie.models.error import Error, ErrorStatus
from oopsie.models.fix_attempt import FixAttemptStatus
from oopsie.services.fix_service import (
    complete_fix_attempt,
    create_fix_attempt,
    generate_branch_name,
    get_fix_attempt_status_for_errors,
    get_fix_attempts_for_error,
    has_active_fix_attempt,
    mark_fix_attempt_running,
)
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import ErrorFactory, OrganizationFactory, ProjectFactory


@pytest.mark.asyncio
async def test_generate_branch_name():
    eid = uuid.UUID("12345678-1234-1234-1234-123456789abc")
    assert generate_branch_name(eid) == "oopsie/fix-12345678"


@pytest.mark.asyncio
async def test_generate_branch_name_from_string():
    result = generate_branch_name("abcdef01-0000-0000-0000-000000000000")
    assert result == "oopsie/fix-abcdef01"


@pytest.mark.asyncio
async def test_create_fix_attempt(db_session: AsyncSession, factory):
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    fa = await create_fix_attempt(db_session, error.id, "oopsie/fix-abc")
    assert fa.error_id == error.id
    assert fa.branch_name == "oopsie/fix-abc"
    assert fa.status == FixAttemptStatus.PENDING
    assert fa.id is not None


@pytest.mark.asyncio
async def test_has_active_fix_attempt_pending(db_session: AsyncSession, factory):
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    await create_fix_attempt(db_session, error.id, "branch")
    result = await has_active_fix_attempt(db_session, error.id)
    assert result is True


@pytest.mark.asyncio
async def test_has_active_fix_attempt_running(db_session: AsyncSession, factory):
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    fa = await create_fix_attempt(db_session, error.id, "branch")
    await mark_fix_attempt_running(db_session, fa.id)
    result = await has_active_fix_attempt(db_session, error.id)
    assert result is True


@pytest.mark.asyncio
async def test_has_active_fix_attempt_success(db_session: AsyncSession, factory):
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    fa = await create_fix_attempt(db_session, error.id, "branch")
    await complete_fix_attempt(
        db_session,
        fa.id,
        success=True,
        pr_url="http://pr",
        claude_output="done",
    )
    result = await has_active_fix_attempt(db_session, error.id)
    assert result is False


@pytest.mark.asyncio
async def test_has_active_fix_attempt_failed(db_session: AsyncSession, factory):
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    fa = await create_fix_attempt(db_session, error.id, "branch")
    await complete_fix_attempt(
        db_session,
        fa.id,
        success=False,
        pr_url=None,
        claude_output="err",
    )
    result = await has_active_fix_attempt(db_session, error.id)
    assert result is False


@pytest.mark.asyncio
async def test_has_active_fix_attempt_none(db_session: AsyncSession, factory):
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    result = await has_active_fix_attempt(db_session, error.id)
    assert result is False


@pytest.mark.asyncio
async def test_mark_fix_attempt_running(db_session: AsyncSession, factory):
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    fa = await create_fix_attempt(db_session, error.id, "branch")
    updated = await mark_fix_attempt_running(db_session, fa.id)
    assert updated.status == FixAttemptStatus.RUNNING
    assert updated.started_at is not None


@pytest.mark.asyncio
async def test_complete_fix_attempt_success(db_session: AsyncSession, factory):
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    fa = await create_fix_attempt(db_session, error.id, "branch")
    completed = await complete_fix_attempt(
        db_session,
        fa.id,
        success=True,
        pr_url="https://github.com/o/r/pull/1",
        claude_output="fixed",
    )
    assert completed.status == FixAttemptStatus.SUCCESS
    assert completed.pr_url == "https://github.com/o/r/pull/1"
    assert completed.claude_output == "fixed"
    assert completed.completed_at is not None

    err = await db_session.get(Error, error.id)
    assert err.status == ErrorStatus.FIX_ATTEMPTED


@pytest.mark.asyncio
async def test_complete_fix_attempt_failure(db_session: AsyncSession, factory):
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    fa = await create_fix_attempt(db_session, error.id, "branch")
    completed = await complete_fix_attempt(
        db_session,
        fa.id,
        success=False,
        pr_url=None,
        claude_output="something broke",
    )
    assert completed.status == FixAttemptStatus.FAILED
    assert completed.pr_url is None
    assert completed.completed_at is not None

    err = await db_session.get(Error, error.id)
    assert err.status == ErrorStatus.OPEN


@pytest.mark.asyncio
async def test_get_fix_attempt_status_for_errors_mixed(
    db_session: AsyncSession, factory
):
    """Test batch status query with various scenarios."""
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    e1 = await factory(ErrorFactory, project_id=project.id, fingerprint="f1")
    e2 = await factory(ErrorFactory, project_id=project.id, fingerprint="f2")
    e3 = await factory(ErrorFactory, project_id=project.id, fingerprint="f3")

    await create_fix_attempt(db_session, e2.id, "branch2")
    fa3 = await create_fix_attempt(db_session, e3.id, "branch3")
    await complete_fix_attempt(
        db_session,
        fa3.id,
        success=True,
        pr_url="http://pr",
        claude_output="ok",
    )

    statuses = await get_fix_attempt_status_for_errors(
        db_session, [e1.id, e2.id, e3.id]
    )
    assert statuses[e1.id] is None
    assert statuses[e2.id] == FixAttemptStatus.PENDING
    assert statuses[e3.id] == FixAttemptStatus.SUCCESS


@pytest.mark.asyncio
async def test_get_fix_attempt_status_for_errors_empty(
    db_session: AsyncSession,
):
    result = await get_fix_attempt_status_for_errors(db_session, [])
    assert result == {}


@pytest.mark.asyncio
async def test_get_fix_attempts_for_error_empty(db_session: AsyncSession, factory):
    """Returns empty list when no attempts exist."""
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    result = await get_fix_attempts_for_error(db_session, error.id)
    assert result == []


@pytest.mark.asyncio
async def test_get_fix_attempts_for_error_ordered_desc(
    db_session: AsyncSession, factory
):
    """Returns all attempts ordered by created_at DESC."""
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    fa1 = await create_fix_attempt(db_session, error.id, "branch-1")
    fa2 = await create_fix_attempt(db_session, error.id, "branch-2")
    await complete_fix_attempt(
        db_session, fa1.id, success=False, pr_url=None, claude_output="err"
    )

    result = await get_fix_attempts_for_error(db_session, error.id)
    assert len(result) == 2
    # Most recent first — fa2 was created after fa1
    assert result[0].id == fa2.id
    assert result[1].id == fa1.id
