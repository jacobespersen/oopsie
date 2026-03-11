"""Tests for oopsie.worker.fix_pipeline."""

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from oopsie.models.error import ErrorStatus
from oopsie.models.fix_attempt import FixAttempt, FixAttemptStatus
from oopsie.models.github_installation import InstallationStatus
from oopsie.services.exceptions import (
    ClaudeCodeError,
    GitHubApiError,
    GitOperationError,
)
from oopsie.worker.fix_pipeline import run_fix_pipeline
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import (
    ErrorFactory,
    GithubInstallationFactory,
    OrganizationFactory,
    ProjectFactory,
)

_WS = "oopsie.services.pipeline_service.worker_session"
_GH = "oopsie.services.pipeline_service.github_service"
_CL = "oopsie.services.pipeline_service.claude_service"
_TF = "oopsie.services.pipeline_service.tempfile"
_SH = "oopsie.services.pipeline_service.shutil"
_GAS = "oopsie.services.github_app_service.get_installation_token"


def _mock_worker_session(db_session):
    """Yield the test db_session without committing."""

    @asynccontextmanager
    async def fake_worker_session():
        yield db_session

    return fake_worker_session


@pytest.mark.asyncio
async def test_happy_path(db_session: AsyncSession, factory):
    """Full pipeline: clone, fix, push, PR, success — token passed to all git calls."""
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    installation = await factory(GithubInstallationFactory, organization_id=org.id)
    with (
        patch(_WS, _mock_worker_session(db_session)),
        patch(_GH) as mock_gh,
        patch(_CL) as mock_claude,
        patch(_TF) as mock_tempfile,
        patch(_SH) as mock_shutil,
        patch(_GAS, new=AsyncMock(return_value="ghs_fake_token")),
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

        # Token must be passed to all three git operations
        mock_gh.clone_repo.assert_called_once()
        clone_args = mock_gh.clone_repo.call_args
        assert (
            clone_args.args[1] == "ghs_fake_token"
            or (len(clone_args.args) > 1 and clone_args.args[1] == "ghs_fake_token")
            or clone_args.kwargs.get("token") == "ghs_fake_token"
        ), f"clone_repo called with unexpected args: {clone_args}"

        mock_gh.create_branch.assert_called_once()
        mock_claude.run_claude_code.assert_called_once()
        mock_gh.commit_and_push.assert_called_once()
        commit_args = mock_gh.commit_and_push.call_args
        assert (
            "ghs_fake_token" in commit_args.args
            or commit_args.kwargs.get("token") == "ghs_fake_token"
        ), f"commit_and_push called with unexpected args: {commit_args}"

        mock_gh.create_pull_request.assert_called_once()
        pr_args = mock_gh.create_pull_request.call_args
        assert (
            "ghs_fake_token" in pr_args.args
            or pr_args.kwargs.get("token") == "ghs_fake_token"
        ), f"create_pull_request called with unexpected args: {pr_args}"

        mock_shutil.rmtree.assert_called_once_with("/tmp/clone-dir", ignore_errors=True)

        result = await db_session.execute(
            select(FixAttempt).where(FixAttempt.error_id == error.id)
        )
        fa = result.scalar_one()
        assert fa.status == FixAttemptStatus.SUCCESS
        assert fa.pr_url == ("https://github.com/owner/repo/pull/42")

    # Suppress unused variable warning
    _ = installation


@pytest.mark.asyncio
async def test_skips_non_open_error(db_session: AsyncSession, factory):
    """Pipeline exits early if error is not OPEN."""
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(
        ErrorFactory, project_id=project.id, status=ErrorStatus.IGNORED
    )

    with (
        patch(_WS, _mock_worker_session(db_session)),
        patch(_GH) as mock_gh,
    ):
        await run_fix_pipeline({}, str(error.id), str(project.id))
        mock_gh.clone_repo.assert_not_called()


@pytest.mark.asyncio
async def test_skips_missing_project(db_session: AsyncSession, factory):
    """Pipeline exits early if project not found."""
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    fake_project_id = str(uuid.uuid4())

    with (
        patch(_WS, _mock_worker_session(db_session)),
        patch(_GH) as mock_gh,
    ):
        await run_fix_pipeline({}, str(error.id), fake_project_id)
        mock_gh.clone_repo.assert_not_called()


@pytest.mark.asyncio
async def test_skips_no_installation(db_session: AsyncSession, factory):
    """Pipeline skips gracefully when org has no GithubInstallation row."""
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)

    with (
        patch(_WS, _mock_worker_session(db_session)),
        patch(_GH) as mock_gh,
    ):
        await run_fix_pipeline({}, str(error.id), str(project.id))

        # No fix attempt should be created, and clone_repo must not be called
        mock_gh.clone_repo.assert_not_called()
        result = await db_session.execute(
            select(FixAttempt).where(FixAttempt.error_id == error.id)
        )
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_skips_suspended_installation(db_session: AsyncSession, factory):
    """Pipeline skips gracefully when org's installation is SUSPENDED."""
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    await factory(
        GithubInstallationFactory,
        organization_id=org.id,
        status=InstallationStatus.SUSPENDED,
    )

    with (
        patch(_WS, _mock_worker_session(db_session)),
        patch(_GH) as mock_gh,
    ):
        await run_fix_pipeline({}, str(error.id), str(project.id))

        # No fix attempt should be created, and clone_repo must not be called
        mock_gh.clone_repo.assert_not_called()
        result = await db_session.execute(
            select(FixAttempt).where(FixAttempt.error_id == error.id)
        )
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_token_fetch_failure_marks_failed(db_session: AsyncSession, factory):
    """When get_installation_token raises, fix attempt is marked FAILED."""
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    await factory(GithubInstallationFactory, organization_id=org.id)

    with (
        patch(_WS, _mock_worker_session(db_session)),
        patch(_GH) as mock_gh,
        patch(_TF) as mock_tempfile,
        patch(_SH),
        patch(_GAS, new=AsyncMock(side_effect=GitHubApiError("token exchange failed"))),
    ):
        mock_tempfile.mkdtemp.return_value = "/tmp/clone-dir"
        mock_gh.parse_repo_owner_name.return_value = ("owner", "repo")

        await run_fix_pipeline({}, str(error.id), str(project.id))

        mock_gh.clone_repo.assert_not_called()

        result = await db_session.execute(
            select(FixAttempt).where(FixAttempt.error_id == error.id)
        )
        fa = result.scalar_one()
        assert fa.status == FixAttemptStatus.FAILED
        assert "token exchange failed" in fa.claude_output


@pytest.mark.asyncio
async def test_no_changes_marks_failed(db_session: AsyncSession, factory):
    """When Claude produces no changes, mark FAILED."""
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    await factory(GithubInstallationFactory, organization_id=org.id)
    with (
        patch(_WS, _mock_worker_session(db_session)),
        patch(_GH) as mock_gh,
        patch(_CL) as mock_claude,
        patch(_TF) as mock_tempfile,
        patch(_SH),
        patch(_GAS, new=AsyncMock(return_value="ghs_fake_token")),
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
async def test_clone_failure_marks_failed(db_session: AsyncSession, factory):
    """When git clone fails, mark FAILED."""
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    await factory(GithubInstallationFactory, organization_id=org.id)
    with (
        patch(_WS, _mock_worker_session(db_session)),
        patch(_GH) as mock_gh,
        patch(_TF) as mock_tempfile,
        patch(_SH) as mock_shutil,
        patch(_GAS, new=AsyncMock(return_value="ghs_fake_token")),
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
async def test_claude_failure_marks_failed(db_session: AsyncSession, factory):
    """When Claude Code fails, mark FAILED."""
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    await factory(GithubInstallationFactory, organization_id=org.id)
    with (
        patch(_WS, _mock_worker_session(db_session)),
        patch(_GH) as mock_gh,
        patch(_CL) as mock_claude,
        patch(_TF) as mock_tempfile,
        patch(_SH),
        patch(_GAS, new=AsyncMock(return_value="ghs_fake_token")),
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
