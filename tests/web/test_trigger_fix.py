"""Tests for the manual fix trigger web route."""

import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from oopsie.api.deps import get_session
from oopsie.config import Settings
from oopsie.main import app
from oopsie.models.error import Error, ErrorStatus
from oopsie.models.fix_attempt import FixAttempt, FixAttemptStatus
from oopsie.models.project import Project
from oopsie.utils.encryption import encrypt_value, hash_api_key
from sqlalchemy.ext.asyncio import AsyncSession

_settings = Settings()
_ENQUEUE = "oopsie.web.projects.enqueue_fix_job"


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """Async HTTP client with session override."""

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as c:
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


@pytest_asyncio.fixture
async def error(db_session: AsyncSession, project: Project) -> Error:
    e = Error(
        project_id=project.id,
        error_class="ValueError",
        message="bad value",
        fingerprint="fp-web-test",
        status=ErrorStatus.OPEN,
    )
    db_session.add(e)
    await db_session.flush()
    return e


@pytest.mark.asyncio
async def test_trigger_fix_happy_path(client, project, error):
    """POST trigger enqueues job and redirects."""
    with patch(_ENQUEUE, new_callable=AsyncMock) as mock_eq:
        resp = await client.post(
            f"/projects/{project.id}/errors/{error.id}/fix",
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert f"/projects/{project.id}/errors" in (resp.headers["location"])
        mock_eq.assert_called_once_with(str(error.id), str(project.id))


@pytest.mark.asyncio
async def test_trigger_fix_project_not_found(client, error):
    """404 when project does not exist."""
    fake_id = uuid.uuid4()
    with patch(_ENQUEUE, new_callable=AsyncMock):
        resp = await client.post(
            f"/projects/{fake_id}/errors/{error.id}/fix",
            follow_redirects=False,
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trigger_fix_error_not_found(client, project):
    """404 when error does not exist."""
    fake_id = uuid.uuid4()
    with patch(_ENQUEUE, new_callable=AsyncMock):
        resp = await client.post(
            f"/projects/{project.id}/errors/{fake_id}/fix",
            follow_redirects=False,
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trigger_fix_error_not_open(client, project, error, db_session):
    """400 when error is not OPEN."""
    error.status = ErrorStatus.IGNORED
    await db_session.flush()

    with patch(_ENQUEUE, new_callable=AsyncMock):
        resp = await client.post(
            f"/projects/{project.id}/errors/{error.id}/fix",
            follow_redirects=False,
        )
        assert resp.status_code == 400


# @pytest.mark.asyncio
# async def test_trigger_fix_active_attempt_exists(client, project, error, db_session):
#     """409 when a fix attempt is already in progress."""
#     # This check is temporarily disabled in the route (has_active_fix_attempt commented out).
#     fa = FixAttempt(
#         error_id=error.id,
#         branch_name="oopsie/fix-existing",
#         status=FixAttemptStatus.RUNNING,
#     )
#     db_session.add(fa)
#     await db_session.flush()
#
#     with patch(_ENQUEUE, new_callable=AsyncMock):
#         resp = await client.post(
#             f"/projects/{project.id}/errors/{error.id}/fix",
#             follow_redirects=False,
#         )
#         assert resp.status_code == 409


@pytest.mark.asyncio
async def test_trigger_fix_error_different_project(client, project, db_session):
    """404 when error belongs to a different project."""
    other_project = Project(
        name="other",
        github_repo_url="https://github.com/o/other",
        github_token_encrypted=encrypt_value("ghp_t", _settings.encryption_key),
        api_key_hash=hash_api_key("key2"),
    )
    db_session.add(other_project)
    await db_session.flush()

    other_error = Error(
        project_id=other_project.id,
        error_class="E",
        message="m",
        fingerprint="fp-other",
        status=ErrorStatus.OPEN,
    )
    db_session.add(other_error)
    await db_session.flush()

    with patch(_ENQUEUE, new_callable=AsyncMock):
        resp = await client.post(
            f"/projects/{project.id}/errors/{other_error.id}/fix",
            follow_redirects=False,
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_errors_page_includes_fix_statuses(client, project, error):
    """GET errors page renders with fix button."""
    resp = await client.get(f"/projects/{project.id}/errors")
    assert resp.status_code == 200
    assert "Fix" in resp.text
