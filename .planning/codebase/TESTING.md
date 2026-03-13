# Testing Patterns

**Analysis Date:** 2026-03-13

## Test Framework

**Runner:**
- `pytest` 7.x with `pytest-asyncio` for async test support
- Config: `pyproject.toml` with `asyncio_mode = "auto"`, `testpaths = ["tests"]`

**Assertion Library:**
- Standard `pytest` assertions (`assert`, `pytest.raises()`)
- No additional assertion libraries

**Run Commands:**
```bash
make test                                            # starts test DB, runs pytest with coverage (90% min)
pytest tests/api/                                    # run specific directory
pytest tests/test_auth.py::test_create_access_token_structure  # run specific test
pytest -v --cov=oopsie --cov-report=term-missing    # verbose with coverage report
```

**Coverage Requirements:**
- Minimum 90% coverage enforced via `pytest-cov` (configured in `pyproject.toml`)
- Test must pass with `pytest -v --cov=oopsie --cov-report=term-missing --cov-fail-under=90`
- Coverage omits `tests/*` directory itself

## Test File Organization

**Location:**
- Tests mirror source structure: `tests/` matches `oopsie/` layout
- Directories: `tests/api/`, `tests/models/`, `tests/services/`, `tests/utils/`, `tests/web/`, `tests/`
- Shared fixtures in single `tests/conftest.py` (not in subdirectories)

**Naming:**
- Test files: `test_*.py` (e.g., `test_auth.py`, `test_errors.py`)
- Test functions: `test_<what_is_being_tested>` (e.g., `test_create_access_token_structure()`)
- Descriptive names that read like specifications

**Structure:**
```
tests/
├── conftest.py              # Single root conftest with all shared fixtures
├── factories.py             # factory-boy factories for all models
├── test_auth.py
├── test_config.py
├── test_fingerprint.py
├── api/
│   ├── test_errors.py
│   ├── test_main.py
│   └── test_rbac_deps.py
├── models/
│   ├── test_error.py
│   ├── test_membership.py
│   └── ...
├── services/
│   └── (test files as needed)
├── utils/
│   ├── test_encryption.py
│   └── ...
└── web/
    ├── test_errors.py
    ├── test_members.py
    ├── test_projects.py
    └── test_github.py
```

## Test Structure

**Suite Organization:**
```python
"""Integration tests for POST /api/v1/errors."""

import pytest
from oopsie.models import Error, ErrorOccurrence
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import ProjectFactory


@pytest.mark.asyncio
async def test_ingest_error_creates_error_and_occurrence(
    api_client,
    db_session: AsyncSession,
    factory,
):
    """POST /api/v1/errors with valid API key returns 202."""
    org = await factory(OrganizationFactory)
    project = await factory(
        ProjectFactory, organization_id=org.id, api_key_hash=hash_api_key(_API_KEY)
    )
    response = await api_client.post(
        "/api/v1/errors",
        headers={"Authorization": f"Bearer {_API_KEY}"},
        json={"error_class": "NoMethodError", "message": "undefined method 'foo'"},
    )
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
```

**Patterns:**
- Module-level docstring describes test scope
- Section comments separate logical test groups: `# -----------\n# JWT creation\n# -----------`
- Each test function has a one-line docstring (summary)
- Async tests marked with `@pytest.mark.asyncio`
- Constants defined at module level (e.g., `_API_KEY = "test-api-key-123"`)
- Arrange-Act-Assert structure implicit (setup via fixtures, action, assertions)

## Mocking

**Framework:** `unittest.mock` (Python stdlib)
- `AsyncMock` for async functions
- `patch` for temporarily replacing objects during tests

**Patterns:**
```python
from unittest.mock import AsyncMock, patch

# Example: mock an external service call
@pytest.mark.asyncio
async def test_something_with_mock():
    with patch("oopsie.services.github_service.create_client") as mock_client:
        mock_client.return_value = AsyncMock()
        # Test code here
```

**What to Mock:**
- External API calls (GitHub, Google OAuth, Anthropic Claude)
- I/O operations that are slow or non-deterministic
- Third-party services that require credentials

**What NOT to Mock:**
- Database operations (use real test database with fixtures)
- Internal service functions (test the full call chain)
- Pure functions like fingerprinting, encryption utilities
- Model relationships and constraints

## Fixtures and Factories

**Test Data:**
All test data created via `factory-boy` factories in `tests/factories.py`:

```python
class OrganizationFactory(factory.Factory):
    class Meta:
        model = Organization

    name = factory.Sequence(lambda n: f"Org {n}")
    slug = factory.Sequence(lambda n: f"org-{n}")


class UserFactory(factory.Factory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user-{n}@example.com")
    name = factory.Sequence(lambda n: f"User {n}")
    google_sub = factory.Sequence(lambda n: f"google-sub-{n}")
```

**Usage:**
- Call `factory_cls.build(**kwargs)` to construct (not persisted)
- Use `await factory(factory_cls, **kwargs)` fixture to build and persist in one call
- Each test calls factories inline rather than using pre-created fixtures

**Location:**
- All factories in single `tests/factories.py`
- No factory definitions scattered across test files
- Shared fixtures in `tests/conftest.py`

## Shared Fixtures (conftest.py)

**Key Fixtures:**

1. **`db_session`** — Per-test DB session in rolled-back transaction
   - Auto-creates test DB if missing (on port 5434)
   - Yields async session; each test runs in separate transaction
   - Rolls back on completion, leaving DB clean

2. **`api_client`** — Async HTTP client wired to test DB
   - Overrides `get_session` dependency to use `db_session`
   - Base URL: `http://test` (ASGI transport, no real network)
   - Used for endpoint integration tests

3. **`authenticated_client`** — HTTP client with valid JWT cookie
   - Includes `access_token` cookie for authenticated requests
   - Uses `current_user` fixture for token generation

4. **`organization`** — Pre-created test org (persisted in `db_session`)
   - Built and flushed before test runs

5. **`current_user`** — Test user with admin membership in test org
   - User persisted with admin role in test organization

6. **`factory`** — Generic factory helper
   - Callable: `await factory(FactoryClass, **kwargs)`
   - Builds, adds to session, flushes, returns object

**Example Usage:**
```python
@pytest.mark.asyncio
async def test_example(api_client, db_session: AsyncSession, factory):
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)

    response = await api_client.get(f"/orgs/{org.slug}/projects")
    assert response.status_code == 200
```

**Setup in conftest.py:**
- Environment variables set at import time (before Settings is instantiated)
- Dummy encryption/JWT keys for tests only (never real secrets)
- Database creation handled by `_ensure_test_database_exists()` if DB doesn't exist
- Dependency overrides cleaned up after each test

## Coverage

**Requirements:** 90% minimum (via `pytest-cov`)

**View Coverage:**
```bash
pytest -v --cov=oopsie --cov-report=term-missing
```

**What's Covered:**
- Omits `tests/` directory from coverage calculation
- Focuses on `oopsie/` source code
- Green coverage report shows % per module and line counts

## Test Types

**Unit Tests:**
- Scope: Single function or method in isolation
- Examples: `test_create_access_token_structure()`, `test_same_inputs_same_fingerprint()`
- No DB access (unless testing ORM constraint directly)
- Execution time: <10ms each

**Integration Tests:**
- Scope: Multiple components working together (endpoint → service → DB)
- Examples: `test_ingest_error_creates_error_and_occurrence()`
- Use `db_session`, `api_client` fixtures
- Verify full request/response cycle and DB state

**Model Tests:**
- Scope: ORM model constraints, relationships, cascade behavior
- Location: `tests/models/test_*.py`
- Test unique constraints, foreign key cascades, relationships
- Example: `test_error_unique_fingerprint_per_project()` verifies `IntegrityError` on duplicate

**E2E Tests:**
- Status: Not currently used
- Would use real running server if added

## Common Patterns

**Async Testing:**
```python
@pytest.mark.asyncio
async def test_create_access_token_structure():
    """Access token contains expected fields."""
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "test@example.com")
    payload = decode_jwt(token)
    assert payload["sub"] == str(user_id)
```

**Error Testing:**
```python
@pytest.mark.asyncio
async def test_decode_jwt_expired():
    """decode_jwt raises ValueError on an expired token."""
    import jwt as _jwt
    from oopsie.config import get_settings

    settings = get_settings()
    now = datetime.now(tz=UTC)
    payload = {
        "jti": str(uuid.uuid4()),
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),
    }
    token = _jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    with pytest.raises(ValueError, match="expired"):
        decode_jwt(token)
```

**Database Constraint Testing:**
```python
@pytest.mark.asyncio
async def test_error_unique_fingerprint_per_project(db_session, factory):
    """Duplicate (project_id, fingerprint) raises IntegrityError."""
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    await factory(ErrorFactory, project_id=project.id, fingerprint="abc123def456")

    error2 = ErrorFactory.build(project_id=project.id, fingerprint="abc123def456")
    db_session.add(error2)
    with pytest.raises(IntegrityError):
        await db_session.flush()
```

**Relationship Testing with eager loading:**
```python
@pytest.mark.asyncio
async def test_error_project_relationship(db_session, factory):
    """Error.project returns the linked Project."""
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)
    error = await factory(ErrorFactory, project_id=project.id)

    result = await db_session.execute(
        select(Error).where(Error.id == error.id).options(selectinload(Error.project))
    )
    error_loaded = result.scalar_one()
    assert error_loaded.project.id == project.id
```

**API Testing with Authentication:**
```python
@pytest.mark.asyncio
async def test_ingest_error_unauthorized_without_api_key(api_client):
    """POST /api/v1/errors without Authorization returns 401."""
    response = await api_client.post(
        "/api/v1/errors",
        json={"error_class": "E", "message": "m"},
    )
    assert response.status_code == 401
```

## Pre-Commit & CI

**Local CI Check (before finishing any task):**
```bash
ruff check . && ruff format --check .   # lint & format
mypy oopsie                              # type check
bandit -r oopsie -ll                     # security scan
pytest -v --cov=oopsie --cov-report=term-missing --cov-fail-under=90  # tests + coverage
```

All steps must pass. These mirror `.github/workflows/ci.yml`.

---

*Testing analysis: 2026-03-13*
