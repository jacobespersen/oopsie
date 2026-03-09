# Oopsie

[![CI](https://github.com/jacobespersen/oopsie/actions/workflows/ci.yml/badge.svg)](https://github.com/jacobespersen/oopsie/actions/workflows/ci.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Oopsie is a self-hosted error tracking service that automatically generates fix PRs using [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Point your application at Oopsie's API, and when errors exceed a configured threshold it clones your repo, diagnoses the issue, and opens a pull request with the fix.

## How It Works

1. **Report** — Your app sends errors to Oopsie's ingestion API (deduplicated by fingerprint)
2. **Track** — Oopsie aggregates occurrences and surfaces errors in a web dashboard
3. **Fix** — When an error crosses the threshold, a background worker invokes Claude Code to analyze the stack trace, write a fix, and open a PR on GitHub

## Architecture

```
┌─────────────┐     POST /api/v1/errors     ┌──────────────┐
│  Your App   │ ──────────────────────────── │   Oopsie     │
└─────────────┘         (API key)           │   FastAPI    │
                                            │   Server     │
                                            └──────┬───────┘
                                                   │
                              ┌─────────────────────┼─────────────────────┐
                              │                     │                     │
                        ┌─────▼─────┐        ┌──────▼──────┐      ┌──────▼──────┐
                        │ PostgreSQL│        │    Redis     │      │   Web UI    │
                        │ (storage) │        │  (job queue) │      │  (Jinja2)   │
                        └───────────┘        └──────┬───────┘      └─────────────┘
                                                    │
                                             ┌──────▼──────┐
                                             │   Worker    │
                                             │ (arq/Claude)│
                                             └──────┬──────┘
                                                    │
                                             ┌──────▼──────┐
                                             │   GitHub    │
                                             │  (fix PRs)  │
                                             └─────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- [Honcho](https://github.com/nickstenning/honcho) (for `make dev`)

### 1. Clone and install

```bash
git clone https://github.com/jacobespersen/oopsie.git
cd oopsie
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Configure environment

```bash
cp .env.example .env
```

Generate the required secrets:

```bash
# Fernet key for encrypting GitHub tokens
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'

# JWT secret for session tokens (min 32 characters)
python -c 'import secrets; print(secrets.token_urlsafe(64))'
```

### 3. Set up Google OAuth

- Go to [Google Cloud Console — Credentials](https://console.cloud.google.com/apis/credentials)
- Create an **OAuth 2.0 Client ID** (Web application)
- Add `http://localhost:8000/auth/callback` as an authorized redirect URI
- Copy the client ID and secret into `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`

### 4. Start services and run

```bash
docker compose up -d        # PostgreSQL on :5433
alembic upgrade head         # apply migrations
make dev                     # starts web server + worker
```

Open [http://localhost:8000](http://localhost:8000) to access the web UI, or [http://localhost:8000/docs](http://localhost:8000/docs) for the interactive API docs.

## Bootstrapping the First User

Oopsie uses invitation-gated registration. To create the first organization and admin:

1. Set `ADMIN_EMAIL=you@example.com` in `.env` (optionally `ORG_NAME=My Org`)
2. Start the server — it seeds the organization and an OWNER invitation on first boot
3. Sign in with the matching Google account at `/auth/login`
4. Invite additional users from the **Members** page

> Bootstrap only runs once and is a no-op if an organization already exists.

## Development

### Running

```bash
make dev        # full stack (web + worker) with hot reload
make web        # API server only (http://localhost:8000)
make worker     # background worker only
make services   # Docker services only
```

| Process  | Command                            |
|----------|------------------------------------|
| `web`    | `uvicorn oopsie.main:app --reload` |
| `worker` | `python run_worker.py`             |

### Testing

Tests use a separate PostgreSQL instance on port 5434:

```bash
docker compose --profile test up -d   # start test DB
pytest                                # run all tests
pytest --cov                          # with coverage (fail_under=90)
```

### Linting & Type Checking

```bash
ruff check .          # lint (E, F, I, N, W, UP rules)
ruff format .         # format
mypy oopsie           # type check
bandit -r oopsie -ll  # security scan
```

### Full CI Check

Run the same checks as CI before pushing:

```bash
ruff check . && ruff format --check .
mypy oopsie
bandit -r oopsie -ll
pytest -v --cov=oopsie --cov-report=term-missing --cov-fail-under=90
```

## Project Structure

```
oopsie/
  main.py          — FastAPI app, middleware, routers
  config.py        — Pydantic Settings (reads .env)
  database.py      — Async SQLAlchemy engine + session factory
  auth.py          — JWT helpers, Google OAuth, invitation gating
  auth_routes.py   — /auth/* endpoints (login, callback, logout)
  api/             — REST API endpoints + dependencies
  models/          — SQLAlchemy ORM models
  services/        — Business logic layer
  utils/           — Encryption, fingerprinting helpers
  web/             — Jinja2 HTML views (projects, errors, members)
  worker/          — Background job processing (arq)
templates/         — Jinja2 templates
alembic/           — Database migrations
tests/             — Test suite (pytest, factory-boy)
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | Async PostgreSQL URL (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Yes | Redis connection URL |
| `ENCRYPTION_KEY` | Yes | Fernet key for encrypting GitHub tokens |
| `JWT_SECRET_KEY` | Yes | At least 32-char secret for signing JWTs |
| `GOOGLE_CLIENT_ID` | Yes | Google OAuth 2.0 client ID |
| `GOOGLE_CLIENT_SECRET` | Yes | Google OAuth 2.0 client secret |
| `ANTHROPIC_API_KEY` | For AI fixes | Claude API key for generating fix PRs |
| `ADMIN_EMAIL` | First deploy | Email to seed the first OWNER invitation |
| `ORG_NAME` | No | Name for bootstrapped org (default: `"Oopsie"`) |
| `TEST_DATABASE_URL` | No | Defaults to `DATABASE_URL` with db name `oopsie_test` |
| `LOG_LEVEL` | No | Default: `INFO` |
| `LOG_FORMAT` | No | `json` (default) or `console` |

## License

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE).
