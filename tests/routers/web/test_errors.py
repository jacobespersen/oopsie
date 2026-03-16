"""Tests for web error routes (list, detail, trigger fix)."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from oopsie.models.error import ErrorStatus
from oopsie.models.fix_attempt import FixAttemptStatus

from tests.factories import ErrorFactory, FixAttemptFactory, ProjectFactory

_ENQUEUE = "oopsie.routers.web.errors.enqueue_fix_job"


# ---------------------------------------------------------------------------
# Errors list page
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_errors_page_empty(
    authenticated_client, current_user, organization, factory
):
    """GET /orgs/{slug}/projects/{id}/errors shows empty state when no errors."""
    project = await factory(
        ProjectFactory, name="test-project", organization_id=organization.id
    )
    pid = str(project.id)
    response = await authenticated_client.get(
        f"/orgs/{organization.slug}/projects/{pid}/errors"
    )
    assert response.status_code == 200
    assert b"project-with-errors" not in response.content
    assert b"test-project" in response.content
    assert b"No errors" in response.content


@pytest.mark.asyncio
async def test_errors_page_with_errors(
    authenticated_client, current_user, organization, factory
):
    """GET /orgs/{slug}/projects/{id}/errors lists errors for the project."""
    project = await factory(
        ProjectFactory, name="project-with-errors", organization_id=organization.id
    )
    await factory(
        ErrorFactory,
        project_id=project.id,
        error_class="NoMethodError",
        message="undefined method 'foo' for nil:NilClass",
        fingerprint="abc123def456",
        occurrence_count=3,
    )
    pid = str(project.id)
    response = await authenticated_client.get(
        f"/orgs/{organization.slug}/projects/{pid}/errors"
    )
    assert response.status_code == 200
    assert b"project-with-errors" in response.content
    assert b"NoMethodError" in response.content
    assert b"undefined method" in response.content
    assert b"3" in response.content


@pytest.mark.asyncio
async def test_errors_page_not_found(authenticated_client, organization):
    """GET /orgs/{slug}/projects/{id}/errors returns 404 for unknown project."""
    fake_id = str(uuid.uuid4())
    response = await authenticated_client.get(
        f"/orgs/{organization.slug}/projects/{fake_id}/errors"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_errors_page_includes_fix_statuses(
    authenticated_client, current_user, organization, factory
):
    """GET errors page renders with fix button."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    await factory(ErrorFactory, project_id=project.id)
    resp = await authenticated_client.get(
        f"/orgs/{organization.slug}/projects/{project.id}/errors"
    )
    assert resp.status_code == 200
    assert "Fix" in resp.text


# ---------------------------------------------------------------------------
# Error detail page
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_error_show_200(
    authenticated_client, current_user, organization, factory
):
    """GET error show page returns 200 with error details."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    error = await factory(
        ErrorFactory,
        project_id=project.id,
        error_class="RuntimeError",
        message="something exploded",
    )
    resp = await authenticated_client.get(
        f"/orgs/{organization.slug}/projects/{project.id}/errors/{error.id}"
    )
    assert resp.status_code == 200
    assert "RuntimeError" in resp.text
    assert "something exploded" in resp.text


@pytest.mark.asyncio
async def test_error_show_renders_stack_trace(
    authenticated_client, current_user, organization, factory
):
    """Stack trace is rendered on the show page."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    error = await factory(
        ErrorFactory,
        project_id=project.id,
        stack_trace=(
            "Traceback (most recent call last):\n"
            "  File 'app.py', line 10\n"
            "RuntimeError: something exploded"
        ),
    )
    resp = await authenticated_client.get(
        f"/orgs/{organization.slug}/projects/{project.id}/errors/{error.id}"
    )
    assert resp.status_code == 200
    assert "Traceback" in resp.text


@pytest.mark.asyncio
async def test_error_show_404_unknown_error(
    authenticated_client, current_user, organization, factory
):
    """404 when error ID does not exist."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    resp = await authenticated_client.get(
        f"/orgs/{organization.slug}/projects/{project.id}/errors/{uuid.uuid4()}"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_error_show_404_unknown_project(
    authenticated_client, current_user, organization, factory
):
    """404 when project ID does not exist."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    error = await factory(ErrorFactory, project_id=project.id)
    resp = await authenticated_client.get(
        f"/orgs/{organization.slug}/projects/{uuid.uuid4()}/errors/{error.id}"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_error_show_404_wrong_project(
    authenticated_client, current_user, organization, factory
):
    """404 when error belongs to a different project."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    other_project = await factory(ProjectFactory, organization_id=organization.id)
    other_error = await factory(
        ErrorFactory, project_id=other_project.id, fingerprint="fp-other-show"
    )

    resp = await authenticated_client.get(
        f"/orgs/{organization.slug}/projects/{project.id}/errors/{other_error.id}"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_error_show_no_fix_attempts_empty_state(
    authenticated_client, current_user, organization, factory
):
    """Empty state message when no fix attempts exist."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    error = await factory(ErrorFactory, project_id=project.id)
    resp = await authenticated_client.get(
        f"/orgs/{organization.slug}/projects/{project.id}/errors/{error.id}"
    )
    assert resp.status_code == 200
    assert "No fix attempts yet" in resp.text


@pytest.mark.asyncio
async def test_error_show_lists_fix_attempts(
    authenticated_client, current_user, organization, factory
):
    """Fix attempts are listed with status and branch."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    error = await factory(ErrorFactory, project_id=project.id)
    await factory(
        FixAttemptFactory,
        error_id=error.id,
        branch_name="oopsie/fix-abc12345",
        status=FixAttemptStatus.FAILED,
        claude_output="Claude tried and failed",
    )

    resp = await authenticated_client.get(
        f"/orgs/{organization.slug}/projects/{project.id}/errors/{error.id}"
    )
    assert resp.status_code == 200
    assert "oopsie/fix-abc12345" in resp.text
    assert "Failed" in resp.text
    assert "Claude tried and failed" in resp.text


# ---------------------------------------------------------------------------
# Trigger fix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_fix_happy_path(
    authenticated_client, current_user, organization, factory
):
    """POST trigger enqueues job and redirects."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    error = await factory(ErrorFactory, project_id=project.id)
    with patch(_ENQUEUE, new_callable=AsyncMock) as mock_eq:
        resp = await authenticated_client.post(
            f"/orgs/{organization.slug}/projects/{project.id}/errors/{error.id}/fix",
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert f"/projects/{project.id}/errors" in (resp.headers["location"])
        mock_eq.assert_called_once_with(str(error.id), str(project.id))


@pytest.mark.asyncio
async def test_trigger_fix_project_not_found(
    authenticated_client, current_user, organization, factory
):
    """404 when project does not exist."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    error = await factory(ErrorFactory, project_id=project.id)
    fake_id = uuid.uuid4()
    with patch(_ENQUEUE, new_callable=AsyncMock):
        resp = await authenticated_client.post(
            f"/orgs/{organization.slug}/projects/{fake_id}/errors/{error.id}/fix",
            follow_redirects=False,
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trigger_fix_error_not_found(
    authenticated_client, current_user, organization, factory
):
    """404 when error does not exist."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    fake_id = uuid.uuid4()
    with patch(_ENQUEUE, new_callable=AsyncMock):
        resp = await authenticated_client.post(
            f"/orgs/{organization.slug}/projects/{project.id}/errors/{fake_id}/fix",
            follow_redirects=False,
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trigger_fix_error_not_open(
    authenticated_client, current_user, organization, factory
):
    """400 when error is not OPEN."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    error = await factory(
        ErrorFactory, project_id=project.id, status=ErrorStatus.IGNORED
    )

    with patch(_ENQUEUE, new_callable=AsyncMock):
        resp = await authenticated_client.post(
            f"/orgs/{organization.slug}/projects/{project.id}/errors/{error.id}/fix",
            follow_redirects=False,
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_trigger_fix_error_different_project(
    authenticated_client, current_user, organization, factory
):
    """404 when error belongs to a different project."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    other_project = await factory(ProjectFactory, organization_id=organization.id)
    other_error = await factory(
        ErrorFactory, project_id=other_project.id, fingerprint="fp-other"
    )

    with patch(_ENQUEUE, new_callable=AsyncMock):
        resp = await authenticated_client.post(
            f"/orgs/{organization.slug}/projects/{project.id}/errors/{other_error.id}/fix",
            follow_redirects=False,
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_errors_page_empty_shows_reporting_instructions(
    authenticated_client, current_user, organization, factory
):
    """Empty errors page shows expanded reporting instructions."""
    project = await factory(
        ProjectFactory, name="test-project", organization_id=organization.id
    )
    resp = await authenticated_client.get(
        f"/orgs/{organization.slug}/projects/{project.id}/errors"
    )
    assert resp.status_code == 200
    assert "Reporting Errors" in resp.text
    assert "oopsie-ruby" in resp.text
    assert "api/v1/errors" in resp.text
    assert '<details class="mt-3" open' in resp.text


@pytest.mark.asyncio
async def test_errors_page_with_errors_shows_collapsed_instructions(
    authenticated_client, current_user, organization, factory
):
    """Errors page with errors shows collapsed reporting instructions."""
    project = await factory(
        ProjectFactory, name="test-project", organization_id=organization.id
    )
    await factory(ErrorFactory, project_id=project.id, fingerprint="fp-instr")
    resp = await authenticated_client.get(
        f"/orgs/{organization.slug}/projects/{project.id}/errors"
    )
    assert resp.status_code == 200
    assert "Reporting Errors" in resp.text
    assert '<details class="mt-3" open' not in resp.text
