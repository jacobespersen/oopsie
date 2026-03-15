# Oopsie

AI-powered error fix service that receives error reports and generates fix PRs using Claude Code.

## Philosophy

- **Production-grade, long-term project** — treat all decisions (architecture, data modeling, test structure, abstractions) as if they'll be maintained for years. No throwaway shortcuts.
- **DRY and centralized** — avoid duplicating logic, fixtures, configuration, or setup across files. One canonical location for each concern.
- **Think before scaffolding** — before creating new files, modules, or abstractions, check if an existing one already covers the need. Prefer extending over duplicating.
- **Consistent patterns** — follow the patterns already established in the codebase. When in doubt, look at how similar things are already done.
- **Ask, don't assume** — if instructions are ambiguous or incomplete, ask for clarification before proceeding. A quick question is always better than building the wrong thing.
- **Consider conventions before implementing** — before writing code, think about established conventions for file organisation, directory structure, and separation of concerns. Don't default to the quickest approach if a better one is standard practice. For example: CSS belongs in `static/css/`, not inline in HTML or at the root of `static/`; JS belongs in `static/js/`; etc.

## Setup

```bash
make setup                    # creates .venv, installs deps, sets up pre-commit hooks
source .venv/bin/activate
docker compose up -d          # postgres on :5433
alembic upgrade head
```

## Run

```bash
uvicorn oopsie.main:app --reload                    # dev server on :8000
LOG_FORMAT=console uvicorn oopsie.main:app --reload  # pretty dev logs
```

## Running Tests

```bash
make test                             # starts test DB + runs pytest with coverage
pytest tests/api/                     # run a subset
```

The `db_session` fixture auto-creates the `oopsie_test` database on port 5434 and rolls back each test. Set `DATABASE_URL` and optionally `TEST_DATABASE_URL` in `.env`.

## Lint & Format

```bash
make lint             # ruff check + ruff format --check + mypy + bandit
ruff check . --fix    # autofix lint issues
ruff format .         # autoformat
```

## Architecture

```
oopsie/
  main.py          — FastAPI app, middleware, routers
  config.py        — pydantic-settings (reads .env)
  database.py      — async SQLAlchemy engine + session factory
  logging.py       — structlog setup, request logging middleware
  auth.py          — Google OAuth, invitation gating
  auth_routes.py   — /auth/* endpoints (login, callback, logout)
  session.py       — Redis-backed session management
  api/             — REST endpoints (errors, projects, orgs) + deps (DI, auth, RBAC)
  models/          — SQLAlchemy ORM (Base, Organization, Membership, Invitation, Project, Error, …)
  services/        — business logic (error, invitation, membership, bootstrap)
  utils/           — encryption (Fernet), fingerprinting
  web/             — Jinja2 HTML views (projects, members)
  worker/          — background job processing (placeholder)
templates/         — Jinja2 templates
alembic/           — DB migrations
```

## Conventions

- **Imports at the top** — all imports belong at the top of the file. The only exception is `tests/conftest.py`, where `os.environ.setdefault()` must run before importing modules that read env vars at import time (those imports use `# noqa: E402`).
- **Python 3.11+**, ruff line-length 88
- **Async everywhere** — async endpoints, `AsyncSession`, `asyncpg` driver
- **SQLAlchemy 2.0 style** — `Mapped[]`, `mapped_column()`, `DeclarativeBase`
- **UUID primary keys** — `uuid.uuid4` default on all models
- **Timezone-aware timestamps** — `DateTime(timezone=True)` with `server_default=func.now()`
- **Structured logging** — `from oopsie.logging import logger; logger.info("event_name", key="value")`. Use snake_case event names.
- **API auth** — Bearer token, hashed API key lookup via `get_project_from_api_key` dependency
- **Web auth** — Redis session via `session_id` cookie; `get_current_user` dep resolves user from session
- **RBAC** — `RequireRole(MemberRole.X)` FastAPI callable-class dependency; extracts `org_slug` from path, looks up user's `Membership`, enforces minimum role hierarchy (MEMBER < ADMIN < OWNER)
- **Org-scoped URLs** — all web routes use `/orgs/{org_slug}/...`; API routes use `/api/v1/orgs/{org_slug}/...`
- **Invitation-gated registration** — new users can only sign up via Google OAuth if a pending `Invitation` exists for their email; existing users bypass the invitation check
- **Bootstrap** — on deploy with `ADMIN_EMAIL` set, `bootstrap_if_needed` seeds the first organization and an OWNER invitation for that email
- **Dependency injection** — FastAPI `Depends()` for sessions (`get_session`) and auth
- **Encryption** — Fernet for GitHub tokens; key via `ENCRYPTION_KEY` env var
- **Error fingerprinting** — deterministic hashing to deduplicate errors
- **Small, testable functions** — keep methods focused on a single responsibility. If a function handles multiple pieces of business logic, split it into smaller functions that can be tested independently. Endpoint handlers should be thin orchestrators (ideally under ~15 lines); extract multi-step logic into service functions or helpers rather than letting route handlers balloon.
- **Comment non-obvious code** — add inline comments when logic isn't immediately self-evident, especially for complex business rules, multi-step flows, workarounds, and constraint rationale. Don't comment the obvious, but err on the side of clarity for anything a new reader would need to pause and reason about.
- **Prefer composition over proliferation** — don't create a new module/file for every small piece of logic. Group related functionality together.
- **Services encapsulate business logic** — keep endpoints thin, delegate to services.
- **Packages before custom code** — before writing custom implementations for common concerns (auth, CSRF, validation, rate limiting, etc.), search for well-maintained packages or SDKs that solve the problem. A battle-tested library with community scrutiny is almost always better than a hand-rolled solution, especially for security-sensitive features. Only write custom code when no suitable package exists or when the package clearly doesn't fit the use case.
- **Reuse before creating** — always check existing utilities, helpers, and patterns before introducing new ones.
- **Keep README current** — when adding or changing env vars, setup steps, CLI commands, architecture, or project structure, update README.md as part of the same change.
- **Pydantic request/response models** — define explicit Pydantic schemas for API input and output. Don't return raw dicts or ORM objects from endpoints.
- **Prevent N+1 queries** — use `selectinload()` / `joinedload()` for relationships accessed in loops or list endpoints. Never lazy-load inside iteration.
- **Session-per-request, flush in services** — services call `session.flush()` to surface errors; the endpoint/middleware handles final commit via the session lifecycle. Don't call `session.commit()` in services.

## Testing

- **Test-driven development** — write tests before implementation when possible. At minimum, all new features must have full test coverage including edge cases, error paths, and boundary conditions.
- **Single root conftest** — all shared fixtures live in `tests/conftest.py`. Do not create additional conftest files in subdirectories unless there is a strong, specific reason.
- **Factory-based test data** — use factory-boy factories in `tests/factories.py` for all test data creation. Inline factory calls per test, no fixture-based test data.
- **No duplicated setup** — if multiple tests need similar setup, add a factory or extend an existing one rather than copy-pasting setup code.
- **Test file organization** — mirrors source structure (`tests/api/`, `tests/models/`, `tests/services/`, etc.).

## Database

- **Dev**: PostgreSQL 16 on `localhost:5433` (docker compose)
- **Test**: PostgreSQL 16 on `localhost:5434` (`docker compose --profile test`)
- **Migrations**: `alembic upgrade head` / `alembic revision --autogenerate -m "description"`
- **URL format**: `postgresql+asyncpg://postgres:postgres@localhost:5433/oopsie`

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | yes | Async PostgreSQL URL |
| `SIGNING_SECRET` | yes | Secret for signing cookies and CSRF tokens (`python -c 'import secrets; print(secrets.token_urlsafe(32))'`) |
| `ENCRYPTION_KEY` | yes (for GitHub tokens) | Fernet key (`python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`) |
| `GOOGLE_CLIENT_ID` | for OAuth login | Google OAuth 2.0 client ID |
| `GOOGLE_CLIENT_SECRET` | for OAuth login | Google OAuth 2.0 client secret |
| `ADMIN_EMAIL` | for bootstrap | Email to seed the first OWNER invitation on first deploy |
| `ORG_NAME` | no | Name for the bootstrapped org (default: `"Oopsie"`) |
| `TEST_DATABASE_URL` | no | Defaults to `DATABASE_URL` with db name `oopsie_test` |
| `LOG_LEVEL` | no | Default: `INFO` |
| `REDIS_URL` | yes | Redis connection URL (e.g. `redis://localhost:6379`) |
| `LOG_FORMAT` | no | `json` (default) or `console` |
| `GITHUB_APP_SLUG` | for install flow | Slug from `github.com/apps/{slug}` (human-readable name) |

## Changelog

Update `CHANGELOG.md` when adding features, fixing bugs, or making breaking changes. Follow [Keep a Changelog](https://keepachangelog.com/) format. Add entries under `[Unreleased]` using the appropriate category: Added, Changed, Deprecated, Removed, Fixed, Security.

## Pre-completion CI Check

Before considering any task complete, run the full CI pipeline locally to catch issues before they reach GitHub:

```bash
ruff check . && ruff format --check .   # lint & format
mypy oopsie                              # type check
bandit -r oopsie -ll                     # security scan
pytest -v --cov=oopsie --cov-report=term-missing --cov-fail-under=90  # tests + coverage
```

These match the steps in `.github/workflows/ci.yml`. All must pass before finishing.

## Git Worktrees

All git worktrees must be created in the `.worktrees` directory at the project root.

## Implementation Plans

When creating implementation plans (via plan mode or otherwise), always save them to the Obsidian vault at:

`/Users/jacobespersen/Library/Mobile Documents/iCloud~md~obsidian/Documents/Jacobs vault/Oopsie/implementation plans/`

Use the Obsidian MCP tools to write the plan as a markdown note. Name the file with the date prefix and a descriptive slug (e.g., `2026-03-01-add-webhook-support.md`). Include the date in the frontmatter.
