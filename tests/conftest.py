"""Pytest fixtures for async DB tests. Creates test DB if missing (see README)."""

import os
import warnings

# Must be set before Settings is imported (it reads env vars at import time).
# These are dummy keys for tests only — never use them outside of tests.
os.environ.setdefault("ENCRYPTION_KEY", "sH0fafIOlcxd9fb7s-lXn4sKh3Kh_sddG68RK6meO6U=")
os.environ.setdefault("SIGNING_SECRET", "test-signing-secret-not-for-production")

# Matches the ENCRYPTION_KEY env var set above. Import this constant in tests
# instead of duplicating the value.
TEST_ENCRYPTION_KEY = "sH0fafIOlcxd9fb7s-lXn4sKh3Kh_sddG68RK6meO6U="

import asyncio  # noqa: E402
from urllib.parse import urlparse, urlunparse  # noqa: E402

import httpx  # noqa: E402
import pytest_asyncio  # noqa: E402
from oopsie.config import Settings  # noqa: E402
from oopsie.deps import get_session  # noqa: E402
from oopsie.main import app  # noqa: E402
from oopsie.models import (  # noqa: E402, F401
    Error,
    FixAttempt,
    Project,
    User,
)
from oopsie.models.base import Base  # noqa: E402
from oopsie.models.membership import MemberRole, Membership  # noqa: E402
from oopsie.session import create_session  # noqa: E402
from sqlalchemy import update  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from tests.factories import (  # noqa: E402
    MembershipFactory,
    OrganizationFactory,
    UserFactory,
)

_settings = Settings()
_test_url = _settings.get_test_database_url()


async def set_membership_role(
    db_session: AsyncSession, user_id, organization_id, role: MemberRole
) -> None:
    """Update the existing membership role for a user in an org.

    Test helper — used by web tests that need to change the role created by
    the current_user fixture.
    """
    await db_session.execute(
        update(Membership)
        .where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
        )
        .values(role=role)
    )
    await db_session.flush()


def _create_test_database_sync() -> bool:
    """Create test database if it does not exist (sync).

    Returns True on success.
    """
    parsed = urlparse(_test_url)
    db_name = (parsed.path or "/").strip("/").split("/")[-1] or "oopsie_test"
    admin_path = "/postgres"
    admin_url = urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            admin_path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )
    dsn = admin_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    def _do_create() -> bool:
        try:
            import psycopg2
            from psycopg2 import sql

            conn = psycopg2.connect(dsn)
            conn.autocommit = True
            try:
                stmt = sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name))
                conn.cursor().execute(stmt)
            except psycopg2.errors.DuplicateDatabase:
                pass
            finally:
                conn.close()
            return True
        except Exception:
            return False

    try:
        return asyncio.get_event_loop().run_in_executor(None, _do_create)
    except Exception:
        return False


async def _ensure_test_database_exists() -> bool:
    """Create test database if it does not exist.

    Returns True if created or exists, False on failure.
    """
    result = await asyncio.get_event_loop().run_in_executor(
        None, _create_test_database_sync
    )
    return result


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession):
    """Async HTTP client wired to the test DB session."""

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
async def organization(db_session: AsyncSession):
    """Create and persist a test organization."""
    org = OrganizationFactory.build()
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def current_user(db_session: AsyncSession, organization) -> User:
    """Create and persist a test user with admin membership in the test org."""
    user = UserFactory.build()
    db_session.add(user)
    await db_session.flush()
    membership = MembershipFactory.build(
        user_id=user.id,
        organization_id=organization.id,
        role=MemberRole.admin,
    )
    db_session.add(membership)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def authenticated_client(
    db_session: AsyncSession, current_user: User, fake_redis
):
    """HTTP client with a valid session cookie and CSRF token for current_user.

    Makes an initial GET to /health to obtain the CSRF cookie, then sets
    the x-csrftoken header on all subsequent requests so that POST/PUT/DELETE
    requests pass CSRF validation automatically.
    """

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    session_token = await create_session(current_user.id)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            cookies={"session_id": session_token},
        ) as client:
            # Fetch the CSRF cookie from any safe endpoint, then set it as
            # a default header so all state-changing requests pass validation.
            await client.get("/health")
            csrf_token = client.cookies.get("csrftoken", "")
            client.headers["x-csrftoken"] = csrf_token
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest_asyncio.fixture
def factory(db_session: AsyncSession):
    """Persist a factory-built object and return it."""

    async def _create(factory_cls, **kwargs):
        obj = factory_cls.build(**kwargs)
        db_session.add(obj)
        await db_session.flush()
        return obj

    return _create


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """Test DB session; each test runs in a rolled-back transaction."""
    url = _test_url
    engine = create_async_engine(url, echo=False)
    try:
        connection = await engine.connect()
    except Exception as e:
        await engine.dispose()
        need_create = (
            "does not exist" in str(e) or "InvalidCatalogName" in type(e).__name__
        )
        if need_create and await _ensure_test_database_exists():
            engine = create_async_engine(url, echo=False)
            connection = await engine.connect()
        elif need_create:
            url = _settings.database_url
            warnings.warn(
                f"Test database not available ({e!s}). Using development database. "
                "Set TEST_DATABASE_URL=postgresql+asyncpg://"
                "postgres:postgres@localhost:5434/oopsie_test "
                "in .env "
                "and run 'docker compose up -d' to use the postgres-test service.",
                UserWarning,
                stacklevel=2,
            )
            engine = create_async_engine(url, echo=False)
            connection = await engine.connect()
        else:
            raise
    try:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
        await connection.commit()
        await connection.begin()
        async with AsyncSession(
            bind=connection,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        ) as session:
            yield session
        await connection.rollback()
    finally:
        await connection.close()
        await engine.dispose()


@pytest_asyncio.fixture
async def fake_redis(monkeypatch):
    """Provide a fakeredis instance and patch oopsie.session.get_redis to use it."""
    import fakeredis.aioredis as fake_aioredis
    import oopsie.session

    fake = fake_aioredis.FakeRedis()

    async def _get_fake_redis():
        return fake

    monkeypatch.setattr(oopsie.session, "get_redis", _get_fake_redis)
    yield fake
    await fake.aclose()
