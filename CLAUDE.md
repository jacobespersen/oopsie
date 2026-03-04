# Oopsie

AI-powered error fix service that receives error reports and generates fix PRs using Claude Code.

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
docker compose up -d          # postgres on :5433
alembic upgrade head
```

## Run

```bash
uvicorn oopsie.main:app --reload                    # dev server on :8000
LOG_FORMAT=console uvicorn oopsie.main:app --reload  # pretty dev logs
```

## Test

```bash
docker compose --profile test up -d   # test postgres on :5434
pytest                                # run all tests
pytest --cov                          # with coverage (fail_under=90)
pytest tests/api/                     # subset
```

The `db_session` fixture auto-creates the `oopsie_test` database on port 5434 and rolls back each test. Set `DATABASE_URL` and optionally `TEST_DATABASE_URL` in `.env`.

## Lint & Format

```bash
ruff check .          # lint (rules: E, F, I, N, W, UP)
ruff check . --fix    # lint + autofix
ruff format .         # format
mypy oopsie           # type check
bandit -r oopsie      # security scan (skips B101 in tests)
```

## Architecture

```
oopsie/
  main.py          — FastAPI app, middleware, routers
  config.py        — pydantic-settings (reads .env)
  database.py      — async SQLAlchemy engine + session factory
  logging.py       — structlog setup, request logging middleware
  api/             — REST endpoints (errors, projects) + deps (DI, auth)
  models/          — SQLAlchemy ORM (Base, Project, Error, ErrorOccurrence, FixAttempt)
  services/        — business logic (error_service)
  utils/           — encryption (Fernet), fingerprinting
  web/             — Jinja2 HTML views (projects)
  worker/          — background job processing (placeholder)
templates/         — Jinja2 templates
alembic/           — DB migrations
```

## Conventions

- **Python 3.11+**, ruff line-length 88
- **Async everywhere** — async endpoints, `AsyncSession`, `asyncpg` driver
- **SQLAlchemy 2.0 style** — `Mapped[]`, `mapped_column()`, `DeclarativeBase`
- **UUID primary keys** — `uuid.uuid4` default on all models
- **Timezone-aware timestamps** — `DateTime(timezone=True)` with `server_default=func.now()`
- **Structured logging** — `from oopsie.logging import logger; logger.info("event_name", key="value")`. Use snake_case event names.
- **API auth** — Bearer token, hashed API key lookup via `get_project_from_api_key` dependency
- **Dependency injection** — FastAPI `Depends()` for sessions (`get_session`) and auth
- **Encryption** — Fernet for GitHub tokens; key via `ENCRYPTION_KEY` env var
- **Error fingerprinting** — deterministic hashing to deduplicate errors
- **Small, testable functions** — keep methods focused on a single responsibility. If a function handles multiple pieces of business logic, split it into smaller functions that can be tested independently.
- **Test-driven development** — write tests before implementation when possible. At minimum, all new features must have full test coverage including edge cases, error paths, and boundary conditions.

## Database

- **Dev**: PostgreSQL 16 on `localhost:5433` (docker compose)
- **Test**: PostgreSQL 16 on `localhost:5434` (`docker compose --profile test`)
- **Migrations**: `alembic upgrade head` / `alembic revision --autogenerate -m "description"`
- **URL format**: `postgresql+asyncpg://postgres:postgres@localhost:5433/oopsie`

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | yes | Async PostgreSQL URL |
| `ENCRYPTION_KEY` | yes (for GitHub tokens) | Fernet key (`python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`) |
| `ANTHROPIC_API_KEY` | for AI features | Claude API key |
| `TEST_DATABASE_URL` | no | Defaults to `DATABASE_URL` with db name `oopsie_test` |
| `LOG_LEVEL` | no | Default: `INFO` |
| `LOG_FORMAT` | no | `json` (default) or `console` |

## Implementation Plans

When creating implementation plans (via plan mode or otherwise), always save them to the Obsidian vault at:

`/Users/jacobespersen/Library/Mobile Documents/iCloud~md~obsidian/Documents/Jacobs vault/Oopsie/implementation plans/`

Use the Obsidian MCP tools to write the plan as a markdown note. Name the file with the date prefix and a descriptive slug (e.g., `2026-03-01-add-webhook-support.md`). Include the date in the frontmatter.
