"""Tests for GET /projects/{project_id}/errors/{error_id}."""

import uuid

import pytest
from oopsie.models.fix_attempt import FixAttemptStatus

from tests.factories import ErrorFactory, FixAttemptFactory, ProjectFactory


@pytest.mark.asyncio
async def test_error_show_200(api_client, factory):
    """GET error show page returns 200 with error details."""
    project = await factory(ProjectFactory)
    error = await factory(
        ErrorFactory,
        project_id=project.id,
        error_class="RuntimeError",
        message="something exploded",
    )
    resp = await api_client.get(f"/projects/{project.id}/errors/{error.id}")
    assert resp.status_code == 200
    assert "RuntimeError" in resp.text
    assert "something exploded" in resp.text


@pytest.mark.asyncio
async def test_error_show_renders_stack_trace(api_client, factory):
    """Stack trace is rendered on the show page."""
    project = await factory(ProjectFactory)
    error = await factory(
        ErrorFactory,
        project_id=project.id,
        stack_trace=(
            "Traceback (most recent call last):\n"
            "  File 'app.py', line 10\n"
            "RuntimeError: something exploded"
        ),
    )
    resp = await api_client.get(f"/projects/{project.id}/errors/{error.id}")
    assert resp.status_code == 200
    assert "Traceback" in resp.text


@pytest.mark.asyncio
async def test_error_show_404_unknown_error(api_client, factory):
    """404 when error ID does not exist."""
    project = await factory(ProjectFactory)
    resp = await api_client.get(f"/projects/{project.id}/errors/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_error_show_404_unknown_project(api_client, factory):
    """404 when project ID does not exist."""
    project = await factory(ProjectFactory)
    error = await factory(ErrorFactory, project_id=project.id)
    resp = await api_client.get(f"/projects/{uuid.uuid4()}/errors/{error.id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_error_show_404_wrong_project(api_client, factory):
    """404 when error belongs to a different project."""
    project = await factory(ProjectFactory)
    other_project = await factory(ProjectFactory)
    other_error = await factory(
        ErrorFactory, project_id=other_project.id, fingerprint="fp-other-show"
    )

    resp = await api_client.get(f"/projects/{project.id}/errors/{other_error.id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_error_show_no_fix_attempts_empty_state(api_client, factory):
    """Empty state message when no fix attempts exist."""
    project = await factory(ProjectFactory)
    error = await factory(ErrorFactory, project_id=project.id)
    resp = await api_client.get(f"/projects/{project.id}/errors/{error.id}")
    assert resp.status_code == 200
    assert "No fix attempts yet" in resp.text


@pytest.mark.asyncio
async def test_error_show_lists_fix_attempts(api_client, factory):
    """Fix attempts are listed with status and branch."""
    project = await factory(ProjectFactory)
    error = await factory(ErrorFactory, project_id=project.id)
    await factory(
        FixAttemptFactory,
        error_id=error.id,
        branch_name="oopsie/fix-abc12345",
        status=FixAttemptStatus.FAILED,
        claude_output="Claude tried and failed",
    )

    resp = await api_client.get(f"/projects/{project.id}/errors/{error.id}")
    assert resp.status_code == 200
    assert "oopsie/fix-abc12345" in resp.text
    assert "Failed" in resp.text
    assert "Claude tried and failed" in resp.text
