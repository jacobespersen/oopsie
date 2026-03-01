"""Tests for project API and web UI endpoints."""

import uuid

import pytest
from oopsie.config import Settings
from oopsie.models import Project
from oopsie.utils.encryption import decrypt_value, hash_api_key
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_settings = Settings()

# --- API endpoints (/api/v1/projects) ---


@pytest.mark.asyncio
async def test_list_projects_empty(api_client):
    """GET /api/v1/projects returns empty list when no projects."""
    response = await api_client.get("/api/v1/projects")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_projects(api_client, project_with_api_key):
    """GET /api/v1/projects returns projects without sensitive fields."""
    response = await api_client.get("/api/v1/projects")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert "id" in data[0]
    assert data[0]["name"] == "test-project"
    assert data[0]["github_repo_url"] == "https://github.com/org/repo"
    assert data[0]["default_branch"] == "main"
    assert data[0]["error_threshold"] == 10
    assert "api_key" not in data[0]
    assert "github_token" not in data[0]


@pytest.mark.asyncio
async def test_get_project(api_client, project_with_api_key):
    """GET /api/v1/projects/{id} returns project."""
    pid = str(project_with_api_key.id)
    response = await api_client.get(f"/api/v1/projects/{pid}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == pid
    assert data["name"] == "test-project"
    assert "api_key" not in data
    assert "github_token" not in data


@pytest.mark.asyncio
async def test_get_project_not_found(api_client):
    """GET /api/v1/projects/{id} returns 404 for unknown id."""
    fake_id = str(uuid.uuid4())
    response = await api_client.get(f"/api/v1/projects/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_project(api_client, db_session: AsyncSession):
    """POST /api/v1/projects creates project and returns api_key."""
    response = await api_client.post(
        "/api/v1/projects",
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
    # github_token is now encrypted in the DB
    assert decrypt_value(
        project.github_token_encrypted, _settings.encryption_key
    ) == "ghp_secret"
    # api_key is hashed — the hash of the returned key should match the DB
    assert project.api_key_hash == hash_api_key(data["api_key"])


@pytest.mark.asyncio
async def test_create_project_with_optional_fields(
    api_client, db_session: AsyncSession
):
    """POST /api/v1/projects accepts default_branch and error_threshold."""
    response = await api_client.post(
        "/api/v1/projects",
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

    resp2 = await api_client.get(f"/api/v1/projects/{data['id']}")
    assert resp2.status_code == 200
    api_data = resp2.json()
    assert api_data["default_branch"] == "develop"
    assert api_data["error_threshold"] == 5

    result = await db_session.execute(
        select(Project).where(Project.name == "optional-fields-app")
    )
    project = result.scalar_one()
    assert project.name == "optional-fields-app"
    assert decrypt_value(
        project.github_token_encrypted, _settings.encryption_key
    ) == "ghp_custom_token"


@pytest.mark.asyncio
async def test_update_project(api_client, project_with_api_key):
    """PUT /api/v1/projects/{id} updates project."""
    pid = str(project_with_api_key.id)
    response = await api_client.put(
        f"/api/v1/projects/{pid}",
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
async def test_update_project_not_found(api_client):
    """PUT /api/v1/projects/{id} returns 404 for unknown id."""
    fake_id = str(uuid.uuid4())
    response = await api_client.put(
        f"/api/v1/projects/{fake_id}",
        json={"name": "x"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_project(
    api_client, db_session: AsyncSession, project_with_api_key
):
    """DELETE /api/v1/projects/{id} removes project."""
    pid = str(project_with_api_key.id)
    response = await api_client.delete(f"/api/v1/projects/{pid}")
    assert response.status_code == 204

    result = await db_session.execute(
        select(Project).where(Project.id == project_with_api_key.id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_project_not_found(api_client):
    """DELETE /api/v1/projects/{id} returns 404 for unknown id."""
    fake_id = str(uuid.uuid4())
    response = await api_client.delete(f"/api/v1/projects/{fake_id}")
    assert response.status_code == 404


# --- Web UI endpoints ---


@pytest.mark.asyncio
async def test_web_list_projects_page(api_client):
    """GET /projects returns HTML projects list."""
    response = await api_client.get("/projects")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert b"Projects" in response.content


@pytest.mark.asyncio
async def test_web_list_projects_shows_project(api_client, project_with_api_key):
    """GET /projects lists existing projects."""
    response = await api_client.get("/projects")
    assert response.status_code == 200
    assert b"test-project" in response.content
    assert b"https://github.com/org/repo" in response.content


@pytest.mark.asyncio
async def test_web_new_project_page(api_client):
    """GET /projects/new returns create form."""
    response = await api_client.get("/projects/new")
    assert response.status_code == 200
    assert b"New Project" in response.content
    assert b"name" in response.content
    assert b"github_repo_url" in response.content


@pytest.mark.asyncio
async def test_web_create_project_redirects(api_client):
    """POST /projects creates project and redirects to created page."""
    response = await api_client.post(
        "/projects",
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
    assert "/projects/" in response.headers["location"]
    assert "/created" in response.headers["location"]
    assert "api_key=" in response.headers["location"]


@pytest.mark.asyncio
async def test_web_create_project_and_verify(api_client, db_session: AsyncSession):
    """POST /projects creates project in DB."""
    response = await api_client.post(
        "/projects",
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


@pytest.mark.asyncio
async def test_web_edit_project_page(api_client, project_with_api_key):
    """GET /projects/{id}/edit returns edit form."""
    pid = str(project_with_api_key.id)
    response = await api_client.get(f"/projects/{pid}/edit")
    assert response.status_code == 200
    assert b"Edit Project" in response.content
    assert b"test-project" in response.content


@pytest.mark.asyncio
async def test_web_edit_project_not_found(api_client):
    """GET /projects/{id}/edit returns 404 for unknown id."""
    fake_id = str(uuid.uuid4())
    response = await api_client.get(f"/projects/{fake_id}/edit")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_web_update_project(api_client, project_with_api_key):
    """POST /projects/{id} updates project and redirects to list."""
    pid = str(project_with_api_key.id)
    response = await api_client.post(
        f"/projects/{pid}",
        data={
            "name": "updated-via-web",
            "github_repo_url": "https://github.com/new/repo",
            "github_token": "",  # keep existing
            "default_branch": "develop",
            "error_threshold": "15",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/projects"

    resp2 = await api_client.get(f"/api/v1/projects/{pid}")
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["name"] == "updated-via-web"
    assert data["default_branch"] == "develop"
    assert data["error_threshold"] == 15


@pytest.mark.asyncio
async def test_web_update_project_with_new_token(
    api_client, db_session: AsyncSession, project_with_api_key
):
    """POST /projects/{id} with non-empty github_token updates the token."""
    pid = str(project_with_api_key.id)
    response = await api_client.post(
        f"/projects/{pid}",
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

    result = await db_session.execute(
        select(Project).where(Project.id == project_with_api_key.id)
    )
    project = result.scalar_one()
    assert project.name == "updated-with-token"
    assert decrypt_value(
        project.github_token_encrypted, _settings.encryption_key
    ) == "ghp_new_token_value"
    assert project.error_threshold == 25


@pytest.mark.asyncio
async def test_web_delete_project(
    api_client, db_session: AsyncSession, project_with_api_key
):
    """POST /projects/{id}/delete removes project."""
    pid = str(project_with_api_key.id)
    response = await api_client.post(
        f"/projects/{pid}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/projects"

    result = await db_session.execute(
        select(Project).where(Project.id == project_with_api_key.id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_web_delete_project_not_found(api_client):
    """POST /projects/{id}/delete returns 404 for unknown project."""
    fake_id = str(uuid.uuid4())
    response = await api_client.post(f"/projects/{fake_id}/delete")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_web_api_key_page(api_client, project_with_api_key):
    """GET /projects/{id}/api-key hidden message (key is hashed, not recoverable)."""
    pid = str(project_with_api_key.id)
    response = await api_client.get(f"/projects/{pid}/api-key")
    assert response.status_code == 200
    assert b"hidden" in response.content
    assert b"Regenerate" in response.content


@pytest.mark.asyncio
async def test_web_api_key_page_with_query_param(api_client, project_with_api_key):
    """GET /projects/{id}/api-key?api_key= shows the given key after regenerate."""
    pid = str(project_with_api_key.id)
    # Use URL with query string so the view receives api_key and uses it (line 101)
    response = await api_client.get(
        f"/projects/{pid}/api-key?api_key=new-key-from-query",
    )
    assert response.status_code == 200
    assert b"new-key-from-query" in response.content
    assert b"Regenerate" in response.content


@pytest.mark.asyncio
async def test_web_regenerate_api_key_not_found(api_client):
    """POST /projects/{id}/regenerate-api-key returns 404 for unknown project."""
    fake_id = str(uuid.uuid4())
    response = await api_client.post(f"/projects/{fake_id}/regenerate-api-key")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_web_regenerate_api_key(
    api_client, db_session: AsyncSession, project_with_api_key
):
    """POST /projects/{id}/regenerate-api-key updates key."""
    pid = str(project_with_api_key.id)
    old_hash = project_with_api_key.api_key_hash
    response = await api_client.post(
        f"/projects/{pid}/regenerate-api-key",
        follow_redirects=True,
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Regenerate" in content

    # Verify DB has new key hash
    result = await db_session.execute(
        select(Project).where(Project.id == project_with_api_key.id)
    )
    project = result.scalar_one()
    assert project.api_key_hash != old_hash


@pytest.mark.asyncio
async def test_web_created_page(api_client, project_with_api_key):
    """GET /projects/{id}/created?api_key= shows API key (after create flow)."""
    pid = str(project_with_api_key.id)
    response = await api_client.get(
        f"/projects/{pid}/created",
        params={"api_key": "test-api-key-123"},
    )
    assert response.status_code == 200
    assert b"test-api-key-123" in response.content
    assert b"Back to Projects" in response.content


@pytest.mark.asyncio
async def test_root_redirects_to_projects(api_client):
    """GET / redirects to /projects."""
    response = await api_client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/projects"


@pytest.mark.asyncio
async def test_web_project_errors_page_empty(api_client, project_with_api_key):
    """GET /projects/{id}/errors shows empty state when no errors."""
    pid = str(project_with_api_key.id)
    response = await api_client.get(f"/projects/{pid}/errors")
    assert response.status_code == 200
    assert b"project-with-errors" not in response.content
    assert b"test-project" in response.content
    assert b"No errors recorded" in response.content


@pytest.mark.asyncio
async def test_web_project_errors_page_with_errors(api_client, project_with_errors):
    """GET /projects/{id}/errors lists errors for the project."""
    pid = str(project_with_errors.id)
    response = await api_client.get(f"/projects/{pid}/errors")
    assert response.status_code == 200
    assert b"project-with-errors" in response.content
    assert b"NoMethodError" in response.content
    assert b"undefined method" in response.content
    assert b"3" in response.content  # occurrence_count


@pytest.mark.asyncio
async def test_web_project_errors_page_not_found(api_client):
    """GET /projects/{id}/errors returns 404 for unknown project."""
    fake_id = str(uuid.uuid4())
    response = await api_client.get(f"/projects/{fake_id}/errors")
    assert response.status_code == 404
