"""Tests for oopsie.worker.fix_pipeline."""

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from oopsie.config import Settings
from oopsie.models.error import Error, ErrorStatus
from oopsie.models.fix_attempt import FixAttempt, FixAttemptStatus
from oopsie.models.project import Project
from oopsie.services.exceptions import (
    ClaudeCodeError,
    GitOperationError,
)
from oopsie.utils.encryption import encrypt_value, hash_api_key
from oopsie.worker.fix_pipeline import run_fix_pipeline
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_settings = Settings()

_WS = "oopsie.services.pipeline_service.worker_session"
_GH = "oopsie.services.pipeline_service.github_service"
_CL = "oopsie.services.pipeline_service.claude_service"
_TF = "oopsie.services.pipeline_service.tempfile"
_SH = "oopsie.services.pipeline_service.shutil"


@pytest.fixture
async def project(db_session: AsyncSession) -> Project:
    p = Project(
        name="pipeline-test",
        github_repo_url="https://github.com/owner/repo",
        github_token_encrypted=encrypt_value("ghp_tok", _settings.encryption_key),
        api_key_hash=hash_api_key("key"),
        default_branch="main",
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
        stack_trace="  File main.py, line 1",
        fingerprint="fp123",
        status=ErrorStatus.OPEN,
    )
    db_session.add(e)
    await db_session.flush()
    return e


def _mock_worker_session(db_session):
    """Yield the test db_session without committing."""

    @asynccontextmanager
    async def fake_worker_session():
        yield db_session

    return fake_worker_session


@pytest.mark.asyncio
async def test_happy_path(
    db_session: AsyncSession,
    project: Project,
    error: Error,
):
    """Full pipeline: clone, fix, push, PR, success."""
    with (
        patch(_WS, _mock_worker_session(db_session)),
        patch(_GH) as mock_gh,
        patch(_CL) as mock_claude,
        patch(_TF) as mock_tempfile,
        patch(_SH) as mock_shutil,
    ):
        mock_tempfile.mkdtemp.return_value = "/tmp/clone-dir"
        mock_gh.parse_repo_owner_name.return_value = (
            "owner",
            "repo",
        )
        mock_gh.clone_repo = AsyncMock()
        mock_gh.create_branch = AsyncMock()
        mock_gh.has_changes = AsyncMock(return_value=True)
        mock_gh.commit_and_push = AsyncMock()
        mock_gh.create_pull_request = AsyncMock(
            return_value="https://github.com/owner/repo/pull/42"
        )
        mock_claude.run_claude_code = AsyncMock(return_value="Fixed the bug")

        await run_fix_pipeline({}, str(error.id), str(project.id))

        mock_gh.clone_repo.assert_called_once()
        mock_gh.create_branch.assert_called_once()
        mock_claude.run_claude_code.assert_called_once()
        mock_gh.commit_and_push.assert_called_once()
        mock_gh.create_pull_request.assert_called_once()
        mock_shutil.rmtree.assert_called_once_with("/tmp/clone-dir", ignore_errors=True)

        result = await db_session.execute(
            select(FixAttempt).where(FixAttempt.error_id == error.id)
        )
        fa = result.scalar_one()
        assert fa.status == FixAttemptStatus.SUCCESS
        assert fa.pr_url == ("https://github.com/owner/repo/pull/42")


@pytest.mark.asyncio
async def test_skips_non_open_error(
    db_session: AsyncSession,
    project: Project,
    error: Error,
):
    """Pipeline exits early if error is not OPEN."""
    error.status = ErrorStatus.IGNORED
    await db_session.flush()

    with (
        patch(_WS, _mock_worker_session(db_session)),
        patch(_GH) as mock_gh,
    ):
        await run_fix_pipeline({}, str(error.id), str(project.id))
        mock_gh.clone_repo.assert_not_called()


@pytest.mark.asyncio
async def test_skips_missing_project(db_session: AsyncSession, error: Error):
    """Pipeline exits early if project not found."""
    fake_project_id = str(uuid.uuid4())

    with (
        patch(_WS, _mock_worker_session(db_session)),
        patch(_GH) as mock_gh,
    ):
        await run_fix_pipeline({}, str(error.id), fake_project_id)
        mock_gh.clone_repo.assert_not_called()


@pytest.mark.asyncio
async def test_no_changes_marks_failed(
    db_session: AsyncSession,
    project: Project,
    error: Error,
):
    """When Claude produces no changes, mark FAILED."""
    with (
        patch(_WS, _mock_worker_session(db_session)),
        patch(_GH) as mock_gh,
        patch(_CL) as mock_claude,
        patch(_TF) as mock_tempfile,
        patch(_SH),
    ):
        mock_tempfile.mkdtemp.return_value = "/tmp/clone-dir"
        mock_gh.parse_repo_owner_name.return_value = (
            "owner",
            "repo",
        )
        mock_gh.clone_repo = AsyncMock()
        mock_gh.create_branch = AsyncMock()
        mock_gh.has_changes = AsyncMock(return_value=False)
        mock_claude.run_claude_code = AsyncMock(return_value="Looked but found nothing")

        await run_fix_pipeline({}, str(error.id), str(project.id))

        mock_gh.commit_and_push.assert_not_called()

        result = await db_session.execute(
            select(FixAttempt).where(FixAttempt.error_id == error.id)
        )
        fa = result.scalar_one()
        assert fa.status == FixAttemptStatus.FAILED
        assert fa.claude_output == "Claude produced no changes"


@pytest.mark.asyncio
async def test_clone_failure_marks_failed(
    db_session: AsyncSession,
    project: Project,
    error: Error,
):
    """When git clone fails, mark FAILED."""
    with (
        patch(_WS, _mock_worker_session(db_session)),
        patch(_GH) as mock_gh,
        patch(_TF) as mock_tempfile,
        patch(_SH) as mock_shutil,
    ):
        mock_tempfile.mkdtemp.return_value = "/tmp/clone-dir"
        mock_gh.parse_repo_owner_name.return_value = (
            "owner",
            "repo",
        )
        mock_gh.clone_repo = AsyncMock(side_effect=GitOperationError("clone failed"))

        await run_fix_pipeline({}, str(error.id), str(project.id))

        result = await db_session.execute(
            select(FixAttempt).where(FixAttempt.error_id == error.id)
        )
        fa = result.scalar_one()
        assert fa.status == FixAttemptStatus.FAILED
        assert "clone failed" in fa.claude_output
        mock_shutil.rmtree.assert_called_once()


@pytest.mark.asyncio
async def test_claude_failure_marks_failed(
    db_session: AsyncSession,
    project: Project,
    error: Error,
):
    """When Claude Code fails, mark FAILED."""
    with (
        patch(_WS, _mock_worker_session(db_session)),
        patch(_GH) as mock_gh,
        patch(_CL) as mock_claude,
        patch(_TF) as mock_tempfile,
        patch(_SH),
    ):
        mock_tempfile.mkdtemp.return_value = "/tmp/clone-dir"
        mock_gh.parse_repo_owner_name.return_value = (
            "owner",
            "repo",
        )
        mock_gh.clone_repo = AsyncMock()
        mock_gh.create_branch = AsyncMock()
        mock_claude.run_claude_code = AsyncMock(
            side_effect=ClaudeCodeError("timed out")
        )

        await run_fix_pipeline({}, str(error.id), str(project.id))

        result = await db_session.execute(
            select(FixAttempt).where(FixAttempt.error_id == error.id)
        )
        fa = result.scalar_one()
        assert fa.status == FixAttemptStatus.FAILED
        assert "timed out" in fa.claude_output
