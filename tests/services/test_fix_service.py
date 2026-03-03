"""Tests for oopsie.services.fix_service."""

import uuid

import pytest
from oopsie.config import Settings
from oopsie.models.error import Error, ErrorStatus
from oopsie.models.fix_attempt import FixAttemptStatus
from oopsie.models.project import Project
from oopsie.services.fix_service import (
    complete_fix_attempt,
    create_fix_attempt,
    generate_branch_name,
    get_fix_attempt_status_for_errors,
    has_active_fix_attempt,
    mark_fix_attempt_running,
)
from oopsie.utils.encryption import encrypt_value, hash_api_key
from sqlalchemy.ext.asyncio import AsyncSession

_settings = Settings()


@pytest.fixture
async def project(db_session: AsyncSession) -> Project:
    p = Project(
        name="fix-test",
        github_repo_url="https://github.com/o/r",
        github_token_encrypted=encrypt_value("ghp_t", _settings.encryption_key),
        api_key_hash=hash_api_key("key"),
    )
    db_session.add(p)
    await db_session.flush()
    return p


@pytest.fixture
async def error(db_session: AsyncSession, project: Project) -> Error:
    e = Error(
        project_id=project.id,
        error_class="ValueError",
        message="bad value",
        fingerprint="abc123",
        status=ErrorStatus.OPEN,
    )
    db_session.add(e)
    await db_session.flush()
    return e


@pytest.mark.asyncio
async def test_generate_branch_name():
    eid = uuid.UUID("12345678-1234-1234-1234-123456789abc")
    assert generate_branch_name(eid) == "oopsie/fix-12345678"


@pytest.mark.asyncio
async def test_generate_branch_name_from_string():
    result = generate_branch_name("abcdef01-0000-0000-0000-000000000000")
    assert result == "oopsie/fix-abcdef01"


@pytest.mark.asyncio
async def test_create_fix_attempt(db_session: AsyncSession, error: Error):
    fa = await create_fix_attempt(db_session, error.id, "oopsie/fix-abc")
    assert fa.error_id == error.id
    assert fa.branch_name == "oopsie/fix-abc"
    assert fa.status == FixAttemptStatus.PENDING
    assert fa.id is not None


@pytest.mark.asyncio
async def test_has_active_fix_attempt_pending(db_session: AsyncSession, error: Error):
    await create_fix_attempt(db_session, error.id, "branch")
    result = await has_active_fix_attempt(db_session, error.id)
    assert result is True


@pytest.mark.asyncio
async def test_has_active_fix_attempt_running(db_session: AsyncSession, error: Error):
    fa = await create_fix_attempt(db_session, error.id, "branch")
    await mark_fix_attempt_running(db_session, fa.id)
    result = await has_active_fix_attempt(db_session, error.id)
    assert result is True


@pytest.mark.asyncio
async def test_has_active_fix_attempt_success(db_session: AsyncSession, error: Error):
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
async def test_has_active_fix_attempt_failed(db_session: AsyncSession, error: Error):
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
async def test_has_active_fix_attempt_none(db_session: AsyncSession, error: Error):
    result = await has_active_fix_attempt(db_session, error.id)
    assert result is False


@pytest.mark.asyncio
async def test_mark_fix_attempt_running(db_session: AsyncSession, error: Error):
    fa = await create_fix_attempt(db_session, error.id, "branch")
    updated = await mark_fix_attempt_running(db_session, fa.id)
    assert updated.status == FixAttemptStatus.RUNNING
    assert updated.started_at is not None


@pytest.mark.asyncio
async def test_complete_fix_attempt_success(db_session: AsyncSession, error: Error):
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
async def test_complete_fix_attempt_failure(db_session: AsyncSession, error: Error):
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
    db_session: AsyncSession, project: Project
):
    """Test batch status query with various scenarios."""
    e1 = Error(
        project_id=project.id,
        error_class="E1",
        message="m1",
        fingerprint="f1",
        status=ErrorStatus.OPEN,
    )
    e2 = Error(
        project_id=project.id,
        error_class="E2",
        message="m2",
        fingerprint="f2",
        status=ErrorStatus.OPEN,
    )
    e3 = Error(
        project_id=project.id,
        error_class="E3",
        message="m3",
        fingerprint="f3",
        status=ErrorStatus.OPEN,
    )
    db_session.add_all([e1, e2, e3])
    await db_session.flush()

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
