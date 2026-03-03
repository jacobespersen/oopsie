"""Shared fixtures for worker tests."""

import pytest_asyncio
from oopsie.config import Settings
from oopsie.models.error import Error, ErrorStatus
from oopsie.models.project import Project
from oopsie.utils.encryption import encrypt_value, hash_api_key
from sqlalchemy.ext.asyncio import AsyncSession

_settings = Settings()


@pytest_asyncio.fixture
async def project(db_session: AsyncSession) -> Project:
    p = Project(
        name="pipeline-test",
        github_repo_url="https://github.com/owner/repo",
        github_token_encrypted=encrypt_value("ghp_tok", _settings.encryption_key),
        api_key_hash=hash_api_key("key"),
        default_branch="main",
    )
    db_session.add(p)
    await db_session.flush()
    return p


@pytest_asyncio.fixture
async def error(db_session: AsyncSession, project: Project) -> Error:
    e = Error(
        project_id=project.id,
        error_class="ValueError",
        message="bad value",
        stack_trace="  File main.py, line 1",
        fingerprint="fp123",
        status=ErrorStatus.OPEN,
    )
    db_session.add(e)
    await db_session.flush()
    return e
