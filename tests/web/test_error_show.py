"""Tests for GET /projects/{project_id}/errors/{error_id}."""

import uuid

import pytest
import pytest_asyncio
from oopsie.config import Settings
from oopsie.models.error import Error, ErrorStatus
from oopsie.models.fix_attempt import FixAttempt, FixAttemptStatus
from oopsie.models.project import Project
from oopsie.utils.encryption import encrypt_value, hash_api_key
from sqlalchemy.ext.asyncio import AsyncSession

_settings = Settings()


@pytest_asyncio.fixture
async def error(db_session: AsyncSession, project: Project) -> Error:
    e = Error(
        project_id=project.id,
        error_class="RuntimeError",
        message="something exploded",
        stack_trace="Traceback (most recent call last):\n  File 'app.py', line 10\nRuntimeError: something exploded",
        fingerprint="fp-show-test",
        status=ErrorStatus.OPEN,
    )
    db_session.add(e)
    await db_session.flush()
    return e


@pytest.mark.asyncio
async def test_error_show_200(client, project, error):
    """GET error show page returns 200 with error details."""
    resp = await client.get(f"/projects/{project.id}/errors/{error.id}")
    assert resp.status_code == 200
    assert "RuntimeError" in resp.text
    assert "something exploded" in resp.text
    assert "something exploded" in resp.text


@pytest.mark.asyncio
async def test_error_show_renders_stack_trace(client, project, error):
    """Stack trace is rendered on the show page."""
    resp = await client.get(f"/projects/{project.id}/errors/{error.id}")
    assert resp.status_code == 200
    assert "Traceback" in resp.text


@pytest.mark.asyncio
async def test_error_show_404_unknown_error(client, project):
    """404 when error ID does not exist."""
    resp = await client.get(f"/projects/{project.id}/errors/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_error_show_404_unknown_project(client, error):
    """404 when project ID does not exist."""
    resp = await client.get(f"/projects/{uuid.uuid4()}/errors/{error.id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_error_show_404_wrong_project(client, project, db_session):
    """404 when error belongs to a different project."""
    other = Project(
        name="other",
        github_repo_url="https://github.com/o/other",
        github_token_encrypted=encrypt_value("ghp_t", _settings.encryption_key),
        api_key_hash=hash_api_key("key2"),
    )
    db_session.add(other)
    await db_session.flush()

    other_error = Error(
        project_id=other.id,
        error_class="E",
        message="m",
        fingerprint="fp-other-show",
        status=ErrorStatus.OPEN,
    )
    db_session.add(other_error)
    await db_session.flush()

    resp = await client.get(f"/projects/{project.id}/errors/{other_error.id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_error_show_no_fix_attempts_empty_state(client, project, error):
    """Empty state message when no fix attempts exist."""
    resp = await client.get(f"/projects/{project.id}/errors/{error.id}")
    assert resp.status_code == 200
    assert "No fix attempts yet" in resp.text


@pytest.mark.asyncio
async def test_error_show_lists_fix_attempts(client, project, error, db_session):
    """Fix attempts are listed with status and branch."""
    fa = FixAttempt(
        error_id=error.id,
        branch_name="oopsie/fix-abc12345",
        status=FixAttemptStatus.FAILED,
        claude_output="Claude tried and failed",
    )
    db_session.add(fa)
    await db_session.flush()

    resp = await client.get(f"/projects/{project.id}/errors/{error.id}")
    assert resp.status_code == 200
    assert "oopsie/fix-abc12345" in resp.text
    assert "Failed" in resp.text
    assert "Claude tried and failed" in resp.text
