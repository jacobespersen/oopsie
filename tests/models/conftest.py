"""Shared fixtures for model tests."""

import pytest_asyncio
from oopsie.config import Settings
from oopsie.models import Error, Project
from oopsie.utils.encryption import encrypt_value, hash_api_key

_settings = Settings()


@pytest_asyncio.fixture
def sample_project_data():
    """Minimal valid data for creating a Project."""
    return {
        "name": "my-app",
        "github_repo_url": "https://github.com/org/repo",
        "github_token_encrypted": encrypt_value("ghp_secret", _settings.encryption_key),
        "api_key_hash": hash_api_key("oopsie-api-key-123"),
    }


@pytest_asyncio.fixture
def sample_error_data(sample_project_data):
    """Minimal valid data for creating an Error (requires project_id from a Project)."""
    return {
        "error_class": "NoMethodError",
        "message": "undefined method 'foo' for nil:NilClass",
        "fingerprint": "abc123def456",
    }


@pytest_asyncio.fixture
async def saved_project(db_session, sample_project_data):
    """Create and persist a project; return it."""
    project = Project(**sample_project_data)
    db_session.add(project)
    await db_session.flush()
    return project


@pytest_asyncio.fixture
async def saved_error(db_session, saved_project, sample_error_data):
    """Create and persist a project and error; return the error."""
    sample_error_data["project_id"] = saved_project.id
    error = Error(**sample_error_data)
    db_session.add(error)
    await db_session.flush()
    return error
