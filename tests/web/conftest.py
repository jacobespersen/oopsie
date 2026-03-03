"""Shared fixtures for web UI tests."""

import httpx
import pytest_asyncio
from oopsie.api.deps import get_session
from oopsie.config import Settings
from oopsie.main import app
from oopsie.models.project import Project
from oopsie.utils.encryption import encrypt_value, hash_api_key
from sqlalchemy.ext.asyncio import AsyncSession

_settings = Settings()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest_asyncio.fixture
async def project(db_session: AsyncSession) -> Project:
    p = Project(
        name="web-test",
        github_repo_url="https://github.com/o/r",
        github_token_encrypted=encrypt_value("ghp_t", _settings.encryption_key),
        api_key_hash=hash_api_key("key"),
    )
    db_session.add(p)
    await db_session.flush()
    return p
