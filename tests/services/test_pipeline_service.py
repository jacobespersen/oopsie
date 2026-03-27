"""Tests for pipeline context enrichment from ErrorOccurrence."""

from unittest.mock import AsyncMock, patch

import pytest
from oopsie.models.fix_attempt import FixAttempt
from oopsie.services.anthropic_key_service import set_anthropic_api_key
from oopsie.worker.fix_pipeline import run_fix_pipeline
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import TEST_ENCRYPTION_KEY
from tests.factories import (
    ErrorFactory,
    ErrorOccurrenceFactory,
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
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_worker_session():
        yield db_session

    return fake_worker_session


def _setup_mocks(mock_gh, mock_claude, mock_tempfile):
    """Wire up the standard happy-path mock returns."""
    mock_tempfile.mkdtemp.return_value = "/tmp/clone-dir"
    mock_gh.parse_repo_owner_name.return_value = ("owner", "repo")
    mock_gh.clone_repo = AsyncMock()
    mock_gh.create_branch = AsyncMock()
    mock_gh.has_changes = AsyncMock(return_value=True)
    mock_gh.commit_and_push = AsyncMock()
    mock_gh.create_pull_request = AsyncMock(
        return_value="https://github.com/owner/repo/pull/1"
    )
    mock_claude.run_claude_code = AsyncMock(return_value="Fixed")


@pytest.mark.asyncio
async def test_pipeline_passes_context_to_claude(db_session: AsyncSession, factory):
    """Pipeline loads occurrence context and passes it to Claude."""
    org = await factory(OrganizationFactory)
    set_anthropic_api_key(org, "sk-ant-test-key", TEST_ENCRYPTION_KEY)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    await factory(GithubInstallationFactory, organization_id=org.id)

    chain = [{"type": "KeyError", "value": "missing key"}]
    ctx = {"type": "http", "description": "POST /api/users"}
    await factory(
        ErrorOccurrenceFactory,
        error_id=error.id,
        exception_chain=chain,
        execution_context=ctx,
    )

    with (
        patch(_WS, _mock_worker_session(db_session)),
        patch(_GH) as mock_gh,
        patch(_CL) as mock_claude,
        patch(_TF) as mock_tempfile,
        patch(_SH),
        patch(_GAS, new=AsyncMock(return_value="ghs_fake_token")),
    ):
        _setup_mocks(mock_gh, mock_claude, mock_tempfile)
        await run_fix_pipeline({}, str(error.id), str(project.id))

        mock_claude.run_claude_code.assert_called_once()
        call_kwargs = mock_claude.run_claude_code.call_args
        assert call_kwargs.kwargs["exception_chain"] == chain
        assert call_kwargs.kwargs["execution_context"] == ctx


@pytest.mark.asyncio
async def test_pipeline_passes_none_context_without_occurrence(
    db_session: AsyncSession, factory
):
    """When no occurrence exists, context fields are None."""
    org = await factory(OrganizationFactory)
    set_anthropic_api_key(org, "sk-ant-test-key", TEST_ENCRYPTION_KEY)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    await factory(GithubInstallationFactory, organization_id=org.id)
    # No ErrorOccurrence created

    with (
        patch(_WS, _mock_worker_session(db_session)),
        patch(_GH) as mock_gh,
        patch(_CL) as mock_claude,
        patch(_TF) as mock_tempfile,
        patch(_SH),
        patch(_GAS, new=AsyncMock(return_value="ghs_fake_token")),
    ):
        _setup_mocks(mock_gh, mock_claude, mock_tempfile)
        await run_fix_pipeline({}, str(error.id), str(project.id))

        call_kwargs = mock_claude.run_claude_code.call_args
        assert call_kwargs.kwargs["exception_chain"] is None
        assert call_kwargs.kwargs["execution_context"] is None


@pytest.mark.asyncio
async def test_pipeline_uses_latest_occurrence_context(
    db_session: AsyncSession, factory
):
    """When multiple occurrences exist, the latest one's context is used."""
    from datetime import UTC, datetime, timedelta

    org = await factory(OrganizationFactory)
    set_anthropic_api_key(org, "sk-ant-test-key", TEST_ENCRYPTION_KEY)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)
    await factory(GithubInstallationFactory, organization_id=org.id)

    now = datetime.now(UTC)
    # Older occurrence with different context
    await factory(
        ErrorOccurrenceFactory,
        error_id=error.id,
        occurred_at=now - timedelta(hours=1),
        exception_chain=[{"type": "OldError", "value": "old"}],
        execution_context={"type": "worker"},
    )
    # Newer occurrence — this should be picked up
    latest_chain = [{"type": "NewError", "value": "new"}]
    latest_ctx = {"type": "http", "description": "GET /health"}
    await factory(
        ErrorOccurrenceFactory,
        error_id=error.id,
        occurred_at=now,
        exception_chain=latest_chain,
        execution_context=latest_ctx,
    )

    with (
        patch(_WS, _mock_worker_session(db_session)),
        patch(_GH) as mock_gh,
        patch(_CL) as mock_claude,
        patch(_TF) as mock_tempfile,
        patch(_SH),
        patch(_GAS, new=AsyncMock(return_value="ghs_fake_token")),
    ):
        _setup_mocks(mock_gh, mock_claude, mock_tempfile)
        await run_fix_pipeline({}, str(error.id), str(project.id))

        call_kwargs = mock_claude.run_claude_code.call_args
        assert call_kwargs.kwargs["exception_chain"] == latest_chain
        assert call_kwargs.kwargs["execution_context"] == latest_ctx

    # Verify fix attempt was created successfully
    result = await db_session.execute(
        select(FixAttempt).where(FixAttempt.error_id == error.id)
    )
    fa = result.scalar_one()
    assert fa.pr_url is not None
