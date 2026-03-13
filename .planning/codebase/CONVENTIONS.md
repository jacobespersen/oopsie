# Coding Conventions

**Analysis Date:** 2026-03-13

## Naming Patterns

**Files:**
- Python modules use `snake_case` (e.g., `error_service.py`, `github_app_service.py`)
- Model files named by entity in singular form (e.g., `user.py`, `error.py`, `membership.py`)
- Test files follow `test_*.py` or `*_test.py` pattern
- Factory files: `factories.py` (single canonical location for all factory-boy factories)
- API endpoint modules group routes by resource (e.g., `oopsie/api/errors.py`)

**Functions:**
- Public functions use `snake_case` (e.g., `compute_fingerprint()`, `upsert_error()`, `create_access_token()`)
- Async functions use `async def` prefix but follow same naming convention
- Private/internal functions prefixed with single underscore (e.g., `_build_google_client()`, `_create_test_database_sync()`)
- Service functions are typically `verb_noun` format (e.g., `upsert_user()`, `accept_invitation()`, `revoke_token()`)

**Variables:**
- Local variables use `snake_case`
- Constants use `UPPERCASE_SNAKE_CASE` (though most config is in `Settings` class)
- Type variables and generics use descriptive names (e.g., `result`, `session`, `payload`)
- Temporary/loop variables follow convention: `for item in items`, `for membership in memberships`

**Types:**
- Enum classes inherit from `enum.StrEnum` or `enum.Enum` and use `UPPERCASE` member names (e.g., `ErrorStatus.OPEN`, `MemberRole.admin`)
- Pydantic models and request/response schemas end with `Body` or are self-descriptive (e.g., `ErrorIngestBody`)
- SQLAlchemy model classes use PascalCase (e.g., `User`, `Error`, `Organization`)
- Exception classes end with `Error` suffix (e.g., `GitOperationError`, `ClaudeCodeError`, `GitHubApiError`)

## Code Style

**Formatting:**
- Line length: 88 characters (via `pyproject.toml` ruff config)
- Python 3.11+ type hints (PEP 604 union syntax: `str | None` instead of `Optional[str]`)
- Trailing commas in multi-line structures

**Linting:**
- Tool: `ruff` with rules `["E", "F", "I", "N", "W", "UP"]`
  - E: pycodestyle errors
  - F: Pyflakes errors
  - I: isort import ordering
  - N: pep8-naming conventions
  - W: warnings
  - UP: pyupgrade modernizations
- Type checking: `mypy` (Python 3.11, warn_return_any=true, warn_unused_ignores=true)
- Security scanning: `bandit` excluding tests, skipping B101 (assert_used — pytest uses asserts)
- No auto-formatting is applied; all code adheres to `ruff format` standards

## Import Organization

**Order:**
1. Standard library imports (`import os`, `from typing import ...`)
2. Third-party imports (`import pytest`, `from sqlalchemy import ...`)
3. Local application imports (`from oopsie.models import ...`)
4. TYPE_CHECKING block at end of imports for circular dependency prevention

**Example from `oopsie/auth.py`:**
```python
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import joinedload

if TYPE_CHECKING:
    from oopsie.models.invitation import Invitation
    from oopsie.models.membership import Membership

import jwt
from authlib.integrations.starlette_client import OAuth
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.config import get_settings
from oopsie.logging import logger
```

**Path Aliases:**
- No path aliases used; all imports are explicit absolute paths
- Relative imports within package are discouraged

## Error Handling

**Exception Hierarchy:**
- Base exception: `OopsieServiceError` in `oopsie/services/exceptions.py`
- Service-specific exceptions inherit from base:
  - `GitOperationError` — git CLI failures
  - `ClaudeCodeError` — Claude Code CLI timeouts/failures
  - `GitHubApiError` — GitHub API call failures
  - `GitHubAppNotConfiguredError` — missing GitHub App credentials

**Patterns:**
- Services raise custom exceptions; endpoints translate to HTTP responses
- Pure functions (e.g., `decode_jwt()`) raise `ValueError` with descriptive messages
- Database operations don't catch IntegrityError unless the constraint is expected (e.g., unique violation tests explicitly expect it)
- Async operations preserve exception type; no exception wrapping except at service boundary

**Example from `oopsie/auth.py`:**
```python
def decode_jwt(token: str) -> dict[str, Any]:
    """Decode a JWT token without DB checks. Raises ValueError on invalid input."""
    settings = get_settings()
    try:
        return jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError as exc:
        raise ValueError(f"Invalid token: {exc}")
```

## Logging

**Framework:** `structlog` with stdlib logging backend

**Patterns:**
- Import global logger: `from oopsie.logging import logger`
- Use snake_case event names: `logger.info("user_created", user_id=str(user.id), email=user.email)`
- Always pass structured data as keyword arguments (not formatted strings)
- Include IDs as strings for readability in logs
- Request correlation via `x-request-id` header auto-bound via `RequestLoggingMiddleware`
- Context-bound values (e.g., request_id) set via `structlog.contextvars.bind_contextvars()`

**Example from `oopsie/services/error_service.py`:**
```python
logger.info(
    "error_created",
    error_id=str(error.id),
    project_id=str(project_id),
    error_class=error_class,
)
```

**Log levels:**
- SQLAlchemy engine logger set to WARNING (too verbose at INFO)
- Default root logger: INFO
- Configurable via `LOG_LEVEL` env var

## Comments

**When to Comment:**
- Non-obvious business logic (e.g., why a constraint exists, why an order matters)
- Complex multi-step flows that benefit from a high-level overview
- Workarounds and known limitations
- DO NOT comment obvious code (e.g., "increment counter by 1")

**JSDoc/TSDoc:**
- All public functions and methods have docstrings
- Format: one-line summary (imperative mood), optional longer description, Args/Returns if not obvious
- Example from `oopsie/auth.py`:
  ```python
  async def decode_jwt_token(token: str, session: AsyncSession) -> dict[str, Any]:
      """Decode JWT and verify it has not been revoked."""
  ```

**Inline Comments:**
- Used sparingly, only for logic that isn't self-documenting
- Example from `oopsie/logging.py`:
  ```python
  # Clear any leftover context from a previous request (connection reuse)
  # and bind the request_id so all downstream logs include it.
  structlog.contextvars.clear_contextvars()
  ```

## Function Design

**Size:** Prefer small, single-responsibility functions
- Thin endpoint handlers (ideally <15 lines) delegate to service functions
- Service functions encapsulate related business logic but stay under ~40 lines
- Helper functions broken out if logic is reused or test-worthy in isolation

**Parameters:**
- Use explicit parameters; avoid *args or **kwargs except where forwarding
- Type hints on all parameters and return values
- Async functions always annotated with `async def`
- Dependency injection via FastAPI `Depends()` for endpoints

**Return Values:**
- Functions are explicit about success vs. failure (exceptions for errors, not None checks)
- Async database operations return the persisted object or raise
- Pure functions return computed values; side effects limited to logging

**Example from `oopsie/auth.py`:**
```python
async def resolve_or_register_user(
    session: AsyncSession, google_user_info: dict[str, Any]
) -> tuple[User, "list[Membership]"]:
    """Authenticate a Google OAuth user, handling invitation-gated registration.

    Returns the user and a list of new Memberships from accepted invitations.
    Raises ValueError with a redirect hint if the user is new and has no invitation.
    """
    google_sub = google_user_info["sub"]
    result = await session.execute(select(User).where(User.google_sub == google_sub))
    existing = result.scalar_one_or_none()
    invitations = await get_pending_invitations(session, google_user_info["email"])
    if existing is None and not invitations:
        raise ValueError("no_invitation")
    user = await upsert_user(session, google_user_info, existing=existing)
    memberships: list[Membership] = []
    for invitation in invitations:
        membership = await accept_invitation(session, invitation, user)
        memberships.append(membership)
    return user, memberships
```

## Module Design

**Exports:**
- Modules use explicit `__all__` where appropriate (e.g., `oopsie/models/__init__.py`)
- Model package exports all public ORM models via `__all__` for convenient imports
- Service modules don't typically use `__all__`; callers import specific functions

**Example from `oopsie/models/__init__.py`:**
```python
from oopsie.models.base import Base
from oopsie.models.error import Error, ErrorStatus
# ... other imports ...

__all__ = [
    "Base",
    "Error",
    "ErrorStatus",
    # ...
]
```

**Barrel Files:**
- `oopsie/models/__init__.py` acts as a barrel, centralizing all model exports
- Other `__init__.py` files are minimal (often just docstring)

## Database & ORM

**SQLAlchemy 2.0 Style:**
- All models use `Mapped[]` and `mapped_column()` (not Column)
- Type hints on all attributes via `Mapped[]`
- UUID primary keys: `Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, server_default=None)`
- Timezone-aware timestamps: `Mapped[datetime] = mapped_column(DateTime(timezone=True), ...)`
- Server-side defaults: `server_default=func.now()` for created_at, onupdate=func.now() for updated_at
- Foreign keys use `ForeignKey("table.column", ondelete="CASCADE")`
- Relationships use `back_populates` and explicit cascade rules

**Example from `oopsie/models/error.py`:**
```python
class Error(Base):
    __tablename__ = "errors"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=None
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    error_class: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    project = relationship("Project", back_populates="errors")
    fix_attempts = relationship(
        "FixAttempt", back_populates="error", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(
            "ix_errors_project_fingerprint",
            "project_id",
            "fingerprint",
            unique=True,
        ),
    )
```

**Query Patterns:**
- Always use `selectinload()` or `joinedload()` for relationships accessed in loops or list endpoints
- Prevent N+1 queries: eager-load related data in single query
- Example from `oopsie/auth.py`:
  ```python
  result = await session.execute(
      select(Membership)
      .options(joinedload(Membership.organization))
      .where(Membership.user_id == user_id)
      .limit(1)
  )
  ```

**Session & Flush:**
- Session is per-request (FastAPI dependency)
- Services call `await session.flush()` to surface constraint violations
- Endpoints/middleware handle final commit via session lifecycle
- Services never call `await session.commit()`

---

*Convention analysis: 2026-03-13*
