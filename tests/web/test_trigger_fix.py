"""Tests for the manual fix trigger web route."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from oopsie.models.error import ErrorStatus

from tests.factories import ErrorFactory, ProjectFactory

_ENQUEUE = "oopsie.web.projects.enqueue_fix_job"


@pytest.mark.asyncio
async def test_trigger_fix_happy_path(authenticated_client, current_user, factory):
    """POST trigger enqueues job and redirects."""
    project = await factory(ProjectFactory, user_id=current_user.id)
    error = await factory(ErrorFactory, project_id=project.id)
    with patch(_ENQUEUE, new_callable=AsyncMock) as mock_eq:
        resp = await authenticated_client.post(
            f"/projects/{project.id}/errors/{error.id}/fix",
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert f"/projects/{project.id}/errors" in (resp.headers["location"])
        mock_eq.assert_called_once_with(str(error.id), str(project.id))


@pytest.mark.asyncio
async def test_trigger_fix_project_not_found(
    authenticated_client, current_user, factory
):
    """404 when project does not exist."""
    project = await factory(ProjectFactory, user_id=current_user.id)
    error = await factory(ErrorFactory, project_id=project.id)
    fake_id = uuid.uuid4()
    with patch(_ENQUEUE, new_callable=AsyncMock):
        resp = await authenticated_client.post(
            f"/projects/{fake_id}/errors/{error.id}/fix",
            follow_redirects=False,
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trigger_fix_error_not_found(authenticated_client, current_user, factory):
    """404 when error does not exist."""
    project = await factory(ProjectFactory, user_id=current_user.id)
    fake_id = uuid.uuid4()
    with patch(_ENQUEUE, new_callable=AsyncMock):
        resp = await authenticated_client.post(
            f"/projects/{project.id}/errors/{fake_id}/fix",
            follow_redirects=False,
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trigger_fix_error_not_open(authenticated_client, current_user, factory):
    """400 when error is not OPEN."""
    project = await factory(ProjectFactory, user_id=current_user.id)
    error = await factory(
        ErrorFactory, project_id=project.id, status=ErrorStatus.IGNORED
    )

    with patch(_ENQUEUE, new_callable=AsyncMock):
        resp = await authenticated_client.post(
            f"/projects/{project.id}/errors/{error.id}/fix",
            follow_redirects=False,
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_trigger_fix_error_different_project(
    authenticated_client, current_user, factory
):
    """404 when error belongs to a different project."""
    project = await factory(ProjectFactory, user_id=current_user.id)
    other_project = await factory(ProjectFactory, user_id=current_user.id)
    other_error = await factory(
        ErrorFactory, project_id=other_project.id, fingerprint="fp-other"
    )

    with patch(_ENQUEUE, new_callable=AsyncMock):
        resp = await authenticated_client.post(
            f"/projects/{project.id}/errors/{other_error.id}/fix",
            follow_redirects=False,
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_errors_page_includes_fix_statuses(
    authenticated_client, current_user, factory
):
    """GET errors page renders with fix button."""
    project = await factory(ProjectFactory, user_id=current_user.id)
    await factory(ErrorFactory, project_id=project.id)
    resp = await authenticated_client.get(f"/projects/{project.id}/errors")
    assert resp.status_code == 200
    assert "Fix" in resp.text
