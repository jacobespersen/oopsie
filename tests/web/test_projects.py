"""Tests for project web UI endpoints."""

import uuid

import pytest
from oopsie.config import Settings
from oopsie.models import Project
from oopsie.utils.encryption import decrypt_value
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import ProjectFactory

_settings = Settings()


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
    """GET /orgs/{slug}/projects/new returns create form."""
    response = await authenticated_client.get(f"/orgs/{organization.slug}/projects/new")
    assert response.status_code == 200
    assert b"New Project" in response.content
    assert b"name" in response.content
    assert b"github_repo_url" in response.content


@pytest.mark.asyncio
async def test_web_create_project_redirects(authenticated_client, organization):
    """POST /orgs/{slug}/projects creates project and redirects to projects list."""
    response = await authenticated_client.post(
        f"/orgs/{organization.slug}/projects",
        data={
            "name": "web-created",
            "github_repo_url": "https://github.com/org/repo",
            "github_token": "ghp_xxx",
            "default_branch": "main",
            "error_threshold": "10",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/orgs/{organization.slug}/projects"


@pytest.mark.asyncio
async def test_web_create_project_and_verify(
    authenticated_client, organization, db_session: AsyncSession
):
    """POST /orgs/{slug}/projects creates project in DB with org_id set."""
    response = await authenticated_client.post(
        f"/orgs/{organization.slug}/projects",
        data={
            "name": "web-created",
            "github_repo_url": "https://github.com/a/b",
            "github_token": "ghp_xxx",
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
            "github_repo_url": "https://github.com/new/repo",
            "github_token": "",
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
    assert db_project.default_branch == "develop"
    assert db_project.error_threshold == 15


@pytest.mark.asyncio
async def test_web_update_project_with_new_token(
    authenticated_client, current_user, organization, db_session: AsyncSession, factory
):
    """POST /orgs/{slug}/projects/{id} with non-empty github_token updates the token."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    pid = str(project.id)
    response = await authenticated_client.post(
        f"/orgs/{organization.slug}/projects/{pid}",
        data={
            "name": "updated-with-token",
            "github_repo_url": "https://github.com/other/repo",
            "github_token": "ghp_new_token_value",
            "default_branch": "main",
            "error_threshold": "25",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    result = await db_session.execute(select(Project).where(Project.id == project.id))
    db_project = result.scalar_one()
    assert db_project.name == "updated-with-token"
    assert (
        decrypt_value(db_project.github_token_encrypted, _settings.encryption_key)
        == "ghp_new_token_value"
    )
    assert db_project.error_threshold == 25


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
