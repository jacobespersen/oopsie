"""Fixtures for API tests."""

import httpx
import pytest_asyncio
from oopsie.api.deps import get_session
from oopsie.config import Settings
from oopsie.main import app
from oopsie.models import Error, Project
from oopsie.utils.encryption import encrypt_value, hash_api_key
from sqlalchemy.ext.asyncio import AsyncSession

_settings = Settings()


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession):
    """Async HTTP client with get_session overridden."""

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest_asyncio.fixture
async def project_with_api_key(db_session: AsyncSession):
    """Create a project with a known api_key for API tests."""
    project = Project(
        name="test-project",
        github_repo_url="https://github.com/org/repo",
        github_token_encrypted=encrypt_value("ghp_test", _settings.encryption_key),
        api_key_hash=hash_api_key("test-api-key-123"),
    )
    db_session.add(project)
    await db_session.flush()
    return project


@pytest_asyncio.fixture
async def project_with_errors(db_session: AsyncSession):
    """Create a project with errors for tests."""
    project = Project(
        name="project-with-errors",
        github_repo_url="https://github.com/org/repo",
        github_token_encrypted=encrypt_value("ghp_test", _settings.encryption_key),
        api_key_hash=hash_api_key("test-api-key-456"),
    )
    db_session.add(project)
    await db_session.flush()
    error = Error(
        project_id=project.id,
        error_class="NoMethodError",
        message="undefined method 'foo' for nil:NilClass",
        fingerprint="abc123def456",
        occurrence_count=3,
    )
    db_session.add(error)
    await db_session.flush()
    return project
