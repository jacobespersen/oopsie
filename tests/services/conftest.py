"""Shared fixtures for service tests."""

import pytest_asyncio
from oopsie.config import Settings
from oopsie.models.project import Project
from oopsie.utils.encryption import encrypt_value, hash_api_key
from sqlalchemy.ext.asyncio import AsyncSession

_settings = Settings()


@pytest_asyncio.fixture
async def project(db_session: AsyncSession) -> Project:
    p = Project(
        name="svc-test",
        github_repo_url="https://github.com/o/r",
        github_token_encrypted=encrypt_value("ghp_t", _settings.encryption_key),
        api_key_hash=hash_api_key("key"),
    )
    db_session.add(p)
    await db_session.flush()
    return p
