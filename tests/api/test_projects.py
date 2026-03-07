"""Tests for project API and web UI endpoints."""

import uuid

import pytest
from oopsie.config import Settings
from oopsie.models import Project
from oopsie.utils.encryption import decrypt_value, hash_api_key
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import ErrorFactory, ProjectFactory

_settings = Settings()


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_projects_requires_auth(api_client):
    """GET /api/v1/orgs/{slug}/projects returns 401 without auth."""
    response = await api_client.get("/api/v1/orgs/any-org/projects")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_projects_empty(authenticated_client, organization):
    """GET /api/v1/orgs/{slug}/projects returns empty list when no projects in org."""
    response = await authenticated_client.get(
        f"/api/v1/orgs/{organization.slug}/projects"
    )
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_projects(authenticated_client, current_user, organization, factory):
    """GET /api/v1/orgs/{slug}/projects returns only projects in the current org."""
    await factory(
        ProjectFactory,
        name="test-project",
        github_repo_url="https://github.com/org/repo",
        api_key_hash=hash_api_key("test-api-key-123"),
        organization_id=organization.id,
    )
    # Project in another org — should not appear
    from tests.factories import OrganizationFactory

    other_org = await factory(OrganizationFactory, slug="other-org-list")
    await factory(ProjectFactory, name="other-project", organization_id=other_org.id)

    response = await authenticated_client.get(
        f"/api/v1/orgs/{organization.slug}/projects"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "test-project"
    assert data[0]["github_repo_url"] == "https://github.com/org/repo"
    assert "api_key" not in data[0]
    assert "github_token" not in data[0]


@pytest.mark.asyncio
async def test_get_project(authenticated_client, current_user, organization, factory):
    """GET /api/v1/orgs/{slug}/projects/{id} returns org project."""
    project = await factory(
        ProjectFactory, name="test-project", organization_id=organization.id
    )
    pid = str(project.id)
    response = await authenticated_client.get(
        f"/api/v1/orgs/{organization.slug}/projects/{pid}"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == pid
    assert data["name"] == "test-project"
    assert "api_key" not in data
    assert "github_token" not in data


@pytest.mark.asyncio
async def test_get_project_not_found(authenticated_client, organization):
    """GET /api/v1/orgs/{slug}/projects/{id} returns 404 for unknown id."""
    fake_id = str(uuid.uuid4())
    response = await authenticated_client.get(
        f"/api/v1/orgs/{organization.slug}/projects/{fake_id}"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_project_other_org_returns_404(
    authenticated_client, organization, factory
):
    """Returns 404 for a project in another org."""
    from tests.factories import OrganizationFactory

    other_org = await factory(OrganizationFactory, slug="other-org-get")
    project = await factory(ProjectFactory, organization_id=other_org.id)
    response = await authenticated_client.get(
        f"/api/v1/orgs/{organization.slug}/projects/{project.id}"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_project(
    authenticated_client, organization, db_session: AsyncSession
):
    """POST /api/v1/orgs/{slug}/projects creates project in org."""
    response = await authenticated_client.post(
        f"/api/v1/orgs/{organization.slug}/projects",
        json={
            "name": "my-app",
            "github_repo_url": "https://github.com/user/repo",
            "github_token": "ghp_secret",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["name"] == "my-app"
    assert "api_key" in data
    assert len(data["api_key"]) > 0

    result = await db_session.execute(select(Project).where(Project.name == "my-app"))
    project = result.scalar_one()
    assert project.name == "my-app"
    assert project.github_repo_url == "https://github.com/user/repo"
    assert (
        decrypt_value(project.github_token_encrypted, _settings.encryption_key)
        == "ghp_secret"
    )
    assert project.api_key_hash == hash_api_key(data["api_key"])
    assert project.organization_id == organization.id


@pytest.mark.asyncio
async def test_create_project_with_optional_fields(
    authenticated_client, organization, db_session: AsyncSession
):
    """POST /api/v1/orgs/{slug}/projects accepts default_branch and error_threshold."""
    response = await authenticated_client.post(
        f"/api/v1/orgs/{organization.slug}/projects",
        json={
            "name": "optional-fields-app",
            "github_repo_url": "https://github.com/user/repo",
            "github_token": "ghp_custom_token",
            "default_branch": "develop",
            "error_threshold": 5,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "optional-fields-app"

    resp2 = await authenticated_client.get(
        f"/api/v1/orgs/{organization.slug}/projects/{data['id']}"
    )
    assert resp2.status_code == 200
    api_data = resp2.json()
    assert api_data["default_branch"] == "develop"
    assert api_data["error_threshold"] == 5

    result = await db_session.execute(
        select(Project).where(Project.name == "optional-fields-app")
    )
    project = result.scalar_one()
    assert (
        decrypt_value(project.github_token_encrypted, _settings.encryption_key)
        == "ghp_custom_token"
    )


@pytest.mark.asyncio
async def test_update_project(
    authenticated_client, current_user, organization, factory
):
    """PUT /api/v1/orgs/{slug}/projects/{id} updates org project."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    pid = str(project.id)
    response = await authenticated_client.put(
        f"/api/v1/orgs/{organization.slug}/projects/{pid}",
        json={
            "name": "updated-name",
            "default_branch": "develop",
            "error_threshold": 20,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "updated-name"
    assert data["default_branch"] == "develop"
    assert data["error_threshold"] == 20


@pytest.mark.asyncio
async def test_update_project_not_found(authenticated_client, organization):
    """PUT /api/v1/orgs/{slug}/projects/{id} returns 404 for unknown id."""
    fake_id = str(uuid.uuid4())
    response = await authenticated_client.put(
        f"/api/v1/orgs/{organization.slug}/projects/{fake_id}",
        json={"name": "x"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_project(
    authenticated_client, current_user, organization, db_session: AsyncSession, factory
):
    """DELETE /api/v1/orgs/{slug}/projects/{id} removes org project."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    pid = str(project.id)
    response = await authenticated_client.delete(
        f"/api/v1/orgs/{organization.slug}/projects/{pid}"
    )
    assert response.status_code == 204

    result = await db_session.execute(select(Project).where(Project.id == project.id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_project_not_found(authenticated_client, organization):
    """DELETE /api/v1/orgs/{slug}/projects/{id} returns 404 for unknown id."""
    fake_id = str(uuid.uuid4())
    response = await authenticated_client.delete(
        f"/api/v1/orgs/{organization.slug}/projects/{fake_id}"
    )
    assert response.status_code == 404


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
    """POST /orgs/{slug}/projects creates project and redirects to created page."""
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
    assert f"/orgs/{organization.slug}/projects/" in response.headers["location"]
    assert "/created" in response.headers["location"]
    assert "api_key=" in response.headers["location"]


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
    assert b"Project Created" in response.content
    assert b"Back to Projects" in response.content

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
    authenticated_client, current_user, organization, factory
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

    resp2 = await authenticated_client.get(
        f"/api/v1/orgs/{organization.slug}/projects/{pid}"
    )
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["name"] == "updated-via-web"
    assert data["default_branch"] == "develop"
    assert data["error_threshold"] == 15


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
async def test_web_api_key_page_with_query_param(
    authenticated_client, current_user, organization, factory
):
    """GET /orgs/{slug}/projects/{id}/api-key?api_key= shows the given key."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    pid = str(project.id)
    response = await authenticated_client.get(
        f"/orgs/{organization.slug}/projects/{pid}/api-key?api_key=new-key-from-query",
    )
    assert response.status_code == 200
    assert b"new-key-from-query" in response.content
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
async def test_web_created_page(
    authenticated_client, current_user, organization, factory
):
    """GET /orgs/{slug}/projects/{id}/created?api_key= shows API key."""
    project = await factory(ProjectFactory, organization_id=organization.id)
    pid = str(project.id)
    response = await authenticated_client.get(
        f"/orgs/{organization.slug}/projects/{pid}/created",
        params={"api_key": "test-api-key-123"},
    )
    assert response.status_code == 200
    assert b"test-api-key-123" in response.content
    assert b"Back to Projects" in response.content


@pytest.mark.asyncio
async def test_root_redirects_to_login(api_client):
    """GET / redirects to /auth/login."""
    response = await api_client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/auth/login"


@pytest.mark.asyncio
async def test_web_project_errors_page_empty(
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
async def test_web_project_errors_page_with_errors(
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
async def test_web_project_errors_page_not_found(authenticated_client, organization):
    """GET /orgs/{slug}/projects/{id}/errors returns 404 for unknown project."""
    fake_id = str(uuid.uuid4())
    response = await authenticated_client.get(
        f"/orgs/{organization.slug}/projects/{fake_id}/errors"
    )
    assert response.status_code == 404
