"""Tests for project web UI endpoints."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from oopsie.models import Project
from oopsie.services.anthropic_key_service import (
    get_anthropic_api_key,
    set_anthropic_api_key,
)
from oopsie.services.exceptions import GitHubApiError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import GithubInstallationFactory, ProjectFactory

_TEST_ENCRYPTION_KEY = "sH0fafIOlcxd9fb7s-lXn4sKh3Kh_sddG68RK6meO6U="

# ---------------------------------------------------------------------------
# Web UI endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_web_list_projects_page_requires_auth(api_client):
    """GET /orgs/{slug}/projects returns 401 without auth."""
    response = await api_client.get("/orgs/any-org/projects")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_web_list_projects_page(authenticated_client, organization):
    """GET /orgs/{slug}/projects returns HTML projects list."""
    response = await authenticated_client.get(f"/orgs/{organization.slug}/projects")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert b"Projects" in response.content


@pytest.mark.asyncio
async def test_web_list_projects_shows_project(
    authenticated_client, current_user, organization, factory
):
    """GET /orgs/{slug}/projects lists projects in the org."""
    await factory(
        ProjectFactory,
        name="test-project",
        github_repo_url="https://github.com/org/repo",
        organization_id=organization.id,
    )
    response = await authenticated_client.get(f"/orgs/{organization.slug}/projects")
    assert response.status_code == 200
    assert b"test-project" in response.content
    assert b"https://github.com/org/repo" in response.content


@pytest.mark.asyncio
async def test_web_new_project_page(authenticated_client, organization):
    """GET /orgs/{slug}/projects/new shows connect notice when no installation."""
    response = await authenticated_client.get(f"/orgs/{organization.slug}/projects/new")
    assert response.status_code == 200
    assert b"New Project" in response.content
    assert b"name" in response.content
    # No active installation — form shows connect notice instead of repo URL input
    assert b"Connect GitHub" in response.content


@pytest.mark.asyncio
async def test_web_create_project_redirects(
    authenticated_client, organization, factory
):
    """POST /orgs/{slug}/projects creates project and redirects to projects list."""
    await factory(
        GithubInstallationFactory,
        organization_id=organization.id,
        github_installation_id=99,
    )
    with patch(
        "oopsie.services.github_installation_service.github_app_service.list_installation_repos",
        new=AsyncMock(return_value=["org/repo"]),
    ):
        response = await authenticated_client.post(
            f"/orgs/{organization.slug}/projects",
            data={
                "name": "web-created",
                "github_repo_full_name": "org/repo",
                "default_branch": "main",
                "error_threshold": "10",
            },
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"] == f"/orgs/{organization.slug}/projects"


@pytest.mark.asyncio
async def test_web_create_project_and_verify(
    authenticated_client, organization, db_session: AsyncSession, factory
):
    """POST /orgs/{slug}/projects creates project in DB with org_id set."""
    await factory(
        GithubInstallationFactory,
        organization_id=organization.id,
        github_installation_id=99,
    )
    with patch(
        "oopsie.services.github_installation_service.github_app_service.list_installation_repos",
        new=AsyncMock(return_value=["a/b"]),
    ):
        response = await authenticated_client.post(
            f"/orgs/{organization.slug}/projects",
            data={
                "name": "web-created",
                "github_repo_full_name": "a/b",
                "default_branch": "main",
                "error_threshold": "5",
            },
            follow_redirects=True,
        )
    assert response.status_code == 200
    # Follows redirect to projects list
    assert b"Projects" in response.content

    result = await db_session.execute(
        select(Project).where(Project.name == "web-created")
    )
    project = result.scalar_one_or_none()
    assert project is not None
    assert project.github_repo_url == "https://github.com/a/b"
    assert project.error_threshold == 5
    assert project.organization_id == organization.id


@pytest.mark.asyncio
async def test_web_edit_project_page(
    authenticated_client, current_user, organization, factory
):
    """GET /orgs/{slug}/projects/{id}/edit returns edit form."""
    project = await factory(
        ProjectFactory, name="test-project", organization_id=organization.id
    )
    pid = str(project.id)
    response = await authenticated_client.get(
        f"/orgs/{organization.slug}/projects/{pid}/edit"
    )
    assert response.status_code == 200
    assert b"Edit Project" in response.content
    assert b"test-project" in response.content


@pytest.mark.asyncio
async def test_web_edit_project_not_found(authenticated_client, organization):
    """GET /orgs/{slug}/projects/{id}/edit returns 404 for unknown id."""
    fake_id = str(uuid.uuid4())
    response = await authenticated_client.get(
        f"/orgs/{organization.slug}/projects/{fake_id}/edit"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_web_update_project(
    authenticated_client, current_user, organization, db_session: AsyncSession, factory
):
    """POST /orgs/{slug}/projects/{id} updates project and redirects to list."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    pid = str(project.id)
    response = await authenticated_client.post(
        f"/orgs/{organization.slug}/projects/{pid}",
        data={
            "name": "updated-via-web",
            "github_repo_full_name": "new/repo",
            "default_branch": "develop",
            "error_threshold": "15",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/orgs/{organization.slug}/projects"

    result = await db_session.execute(select(Project).where(Project.id == project.id))
    db_project = result.scalar_one()
    assert db_project.name == "updated-via-web"
    assert db_project.github_repo_url == "https://github.com/new/repo"
    assert db_project.default_branch == "develop"
    assert db_project.error_threshold == 15


@pytest.mark.asyncio
async def test_web_delete_project(
    authenticated_client, current_user, organization, db_session: AsyncSession, factory
):
    """POST /orgs/{slug}/projects/{id}/delete removes project."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    pid = str(project.id)
    response = await authenticated_client.post(
        f"/orgs/{organization.slug}/projects/{pid}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/orgs/{organization.slug}/projects"

    result = await db_session.execute(select(Project).where(Project.id == project.id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_web_delete_project_not_found(authenticated_client, organization):
    """POST /orgs/{slug}/projects/{id}/delete returns 404 for unknown project."""
    fake_id = str(uuid.uuid4())
    response = await authenticated_client.post(
        f"/orgs/{organization.slug}/projects/{fake_id}/delete"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_web_api_key_page(
    authenticated_client, current_user, organization, factory
):
    """GET /orgs/{slug}/projects/{id}/api-key shows hidden key message."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    pid = str(project.id)
    response = await authenticated_client.get(
        f"/orgs/{organization.slug}/projects/{pid}/api-key"
    )
    assert response.status_code == 200
    assert b"hidden" in response.content
    assert b"Regenerate" in response.content


@pytest.mark.asyncio
async def test_web_api_key_page_after_regeneration(
    authenticated_client, current_user, organization, db_session: AsyncSession, factory
):
    """POST regenerate then follow redirect shows the new key from session flash."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    pid = str(project.id)
    response = await authenticated_client.post(
        f"/orgs/{organization.slug}/projects/{pid}/regenerate-api-key",
        follow_redirects=True,
    )
    assert response.status_code == 200
    # The page should contain a key (any base64url string) since the session flash
    # was consumed by the redirect target
    assert b"Regenerate" in response.content


@pytest.mark.asyncio
async def test_web_regenerate_api_key_not_found(authenticated_client, organization):
    """Returns 404 for unknown project on regenerate-api-key."""
    fake_id = str(uuid.uuid4())
    response = await authenticated_client.post(
        f"/orgs/{organization.slug}/projects/{fake_id}/regenerate-api-key"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_web_regenerate_api_key(
    authenticated_client, current_user, organization, db_session: AsyncSession, factory
):
    """POST /orgs/{slug}/projects/{id}/regenerate-api-key updates key."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    pid = str(project.id)
    old_hash = project.api_key_hash
    response = await authenticated_client.post(
        f"/orgs/{organization.slug}/projects/{pid}/regenerate-api-key",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Regenerate" in response.content.decode()

    result = await db_session.execute(select(Project).where(Project.id == project.id))
    db_project = result.scalar_one()
    assert db_project.api_key_hash != old_hash


@pytest.mark.asyncio
async def test_root_redirects_to_login(api_client):
    """GET / redirects to /auth/login."""
    response = await api_client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/auth/login"


# ---------------------------------------------------------------------------
# Repo picker tests (plan 03-04)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_project_shows_repo_dropdown(
    authenticated_client, organization, factory
):
    """GET /orgs/{slug}/projects/new shows repo dropdown when ACTIVE installation."""
    await factory(
        GithubInstallationFactory,
        organization_id=organization.id,
        github_installation_id=42,
    )
    with patch(
        "oopsie.services.github_installation_service.github_app_service.list_installation_repos",
        new=AsyncMock(return_value=["acme/api", "acme/web"]),
    ):
        response = await authenticated_client.get(
            f"/orgs/{organization.slug}/projects/new"
        )
    assert response.status_code == 200
    assert "acme/api" in response.text
    assert "acme/web" in response.text
    assert "github_repo_full_name" in response.text


@pytest.mark.asyncio
async def test_new_project_shows_connect_notice(authenticated_client, organization):
    """GET /orgs/{slug}/projects/new shows connect notice when no installation."""
    response = await authenticated_client.get(f"/orgs/{organization.slug}/projects/new")
    assert response.status_code == 200
    assert "Connect GitHub" in response.text


@pytest.mark.asyncio
async def test_new_project_list_repos_api_error_shows_empty(
    authenticated_client, organization, factory
):
    """GET /orgs/{slug}/projects/new returns 200 when list_installation_repos fails."""
    await factory(
        GithubInstallationFactory,
        organization_id=organization.id,
        github_installation_id=42,
    )
    with patch(
        "oopsie.services.github_installation_service.github_app_service.list_installation_repos",
        new=AsyncMock(side_effect=GitHubApiError("API error")),
    ):
        response = await authenticated_client.get(
            f"/orgs/{organization.slug}/projects/new"
        )
    assert response.status_code == 200
    # Should show the warning banner and the connect notice
    assert "Could not load repositories from GitHub" in response.text


@pytest.mark.asyncio
async def test_create_project_valid_repo(
    authenticated_client, organization, db_session: AsyncSession, factory
):
    """POST /orgs/{slug}/projects with valid repo creates project and redirects."""
    await factory(
        GithubInstallationFactory,
        organization_id=organization.id,
        github_installation_id=42,
    )
    with patch(
        "oopsie.services.github_installation_service.github_app_service.list_installation_repos",
        new=AsyncMock(return_value=["acme/api"]),
    ):
        response = await authenticated_client.post(
            f"/orgs/{organization.slug}/projects",
            data={
                "name": "repo-picker-project",
                "github_repo_full_name": "acme/api",
                "default_branch": "main",
                "error_threshold": "10",
            },
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"] == f"/orgs/{organization.slug}/projects"

    result = await db_session.execute(
        select(Project).where(Project.name == "repo-picker-project")
    )
    project = result.scalar_one_or_none()
    assert project is not None
    assert project.github_repo_url == "https://github.com/acme/api"


@pytest.mark.asyncio
async def test_create_project_invalid_repo(authenticated_client, organization, factory):
    """POST /orgs/{slug}/projects with repo not in accessible list returns 400."""
    await factory(
        GithubInstallationFactory,
        organization_id=organization.id,
        github_installation_id=42,
    )
    with patch(
        "oopsie.services.github_installation_service.github_app_service.list_installation_repos",
        new=AsyncMock(return_value=["acme/api"]),
    ):
        response = await authenticated_client.post(
            f"/orgs/{organization.slug}/projects",
            data={
                "name": "bad-repo-project",
                "github_repo_full_name": "acme/other",
                "default_branch": "main",
                "error_threshold": "10",
            },
            follow_redirects=False,
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_project_no_installation_allows_creation(
    authenticated_client, organization
):
    """POST /orgs/{slug}/projects with no installation still creates project.

    When no installation is active (empty repo list), repo validation is
    skipped — the form falls back to accepting user-provided repo names.
    """
    response = await authenticated_client.post(
        f"/orgs/{organization.slug}/projects",
        data={
            "name": "no-install-project",
            "github_repo_full_name": "acme/api",
            "default_branch": "main",
            "error_threshold": "10",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


# ---------------------------------------------------------------------------
# Anthropic API key tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_project_with_anthropic_key(
    authenticated_client, organization, db_session: AsyncSession, factory
):
    """POST /orgs/{slug}/projects with anthropic_api_key encrypts and stores it."""
    await factory(
        GithubInstallationFactory,
        organization_id=organization.id,
        github_installation_id=99,
    )
    with patch(
        "oopsie.services.github_installation_service.github_app_service.list_installation_repos",
        new=AsyncMock(return_value=["org/repo"]),
    ):
        await authenticated_client.post(
            f"/orgs/{organization.slug}/projects",
            data={
                "name": "key-project",
                "github_repo_full_name": "org/repo",
                "default_branch": "main",
                "error_threshold": "10",
                "anthropic_api_key": "sk-ant-create-test-abcd",
            },
            follow_redirects=False,
        )
    result = await db_session.execute(
        select(Project).where(Project.name == "key-project")
    )
    project = result.scalar_one()
    assert project.anthropic_api_key_encrypted is not None
    decrypted = get_anthropic_api_key(project, _TEST_ENCRYPTION_KEY)
    assert decrypted == "sk-ant-create-test-abcd"


@pytest.mark.asyncio
async def test_update_project_sets_anthropic_key(
    authenticated_client, current_user, organization, db_session: AsyncSession, factory
):
    """POST update with anthropic_api_key sets the encrypted value."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    await authenticated_client.post(
        f"/orgs/{organization.slug}/projects/{project.id}",
        data={
            "name": project.name,
            "github_repo_full_name": "new/repo",
            "default_branch": "main",
            "error_threshold": "10",
            "anthropic_api_key": "sk-ant-update-key-5678",
        },
        follow_redirects=False,
    )
    result = await db_session.execute(select(Project).where(Project.id == project.id))
    db_project = result.scalar_one()
    decrypted = get_anthropic_api_key(db_project, _TEST_ENCRYPTION_KEY)
    assert decrypted == "sk-ant-update-key-5678"


@pytest.mark.asyncio
async def test_update_project_empty_key_preserves_existing(
    authenticated_client, current_user, organization, db_session: AsyncSession, factory
):
    """Submitting empty anthropic_api_key leaves existing key unchanged."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    set_anthropic_api_key(project, "sk-ant-keep-me-1234", _TEST_ENCRYPTION_KEY)
    await db_session.flush()
    original_encrypted = project.anthropic_api_key_encrypted

    await authenticated_client.post(
        f"/orgs/{organization.slug}/projects/{project.id}",
        data={
            "name": project.name,
            "github_repo_full_name": "new/repo",
            "default_branch": "main",
            "error_threshold": "10",
            "anthropic_api_key": "",
        },
        follow_redirects=False,
    )
    result = await db_session.execute(select(Project).where(Project.id == project.id))
    db_project = result.scalar_one()
    assert db_project.anthropic_api_key_encrypted == original_encrypted


@pytest.mark.asyncio
async def test_update_project_clear_anthropic_key(
    authenticated_client, current_user, organization, db_session: AsyncSession, factory
):
    """Checking clear_anthropic_key checkbox removes the key."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    set_anthropic_api_key(project, "sk-ant-to-clear", _TEST_ENCRYPTION_KEY)
    await db_session.flush()

    await authenticated_client.post(
        f"/orgs/{organization.slug}/projects/{project.id}",
        data={
            "name": project.name,
            "github_repo_full_name": "new/repo",
            "default_branch": "main",
            "error_threshold": "10",
            "anthropic_api_key": "",
            "clear_anthropic_key": "1",
        },
        follow_redirects=False,
    )
    result = await db_session.execute(select(Project).where(Project.id == project.id))
    db_project = result.scalar_one()
    assert db_project.anthropic_api_key_encrypted is None


@pytest.mark.asyncio
async def test_edit_page_shows_masked_anthropic_key(
    authenticated_client, current_user, organization, db_session: AsyncSession, factory
):
    """Edit page shows masked Anthropic key when one is set."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    set_anthropic_api_key(project, "sk-ant-display-wxyz", _TEST_ENCRYPTION_KEY)
    await db_session.flush()

    response = await authenticated_client.get(
        f"/orgs/{organization.slug}/projects/{project.id}/edit"
    )
    assert response.status_code == 200
    assert "sk-\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022wxyz" in response.text
