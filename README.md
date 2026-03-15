# Oopsie

[![CI](https://github.com/jacobespersen/oopsie/actions/workflows/ci.yml/badge.svg)](https://github.com/jacobespersen/oopsie/actions/workflows/ci.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Oopsie is a self-hosted error tracking service that automatically generates fix PRs using [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Point your application at Oopsie's API, and when errors exceed a configured threshold it clones your repo, diagnoses the issue, and opens a pull request with the fix.

## How It Works

1. **Report** — Your app sends errors to Oopsie's ingestion API (deduplicated by fingerprint)
2. **Track** — Oopsie aggregates occurrences and surfaces errors in a web dashboard
3. **Fix** — When an error crosses the threshold, a background worker invokes Claude Code to analyze the stack trace, write a fix, and open a PR on GitHub

## Client Libraries

| Language | Gem / Package | Description |
|----------|---------------|-------------|
| Ruby | [`oopsie-ruby`](https://github.com/jacobespersen/oopsie-ruby) | Lightweight gem with Rack middleware and manual reporting — zero runtime dependencies |

## Architecture

```
┌─────────────┐     POST /api/v1/errors     ┌──────────────┐
│  Your App   │ ────────────────────────────│   Oopsie     │
└─────────────┘         (API key)           │   FastAPI    │
                                            │   Server     │
                                            └──────┬───────┘
                                                   │
                              ┌─────────────────────┼─────────────────────┐
                              │                     │                     │
                        ┌─────▼─────┐        ┌──────▼───────┐      ┌──────▼──────┐
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
make setup              # creates venv, installs deps, sets up pre-commit hooks
source .venv/bin/activate
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

### 4. Set up the GitHub App

Oopsie uses a GitHub App to clone repositories and open fix PRs on your behalf.

**Create the app**

1. Go to [GitHub Developer Settings — New GitHub App](https://github.com/settings/apps/new)
2. Fill in the basic details:
   - **GitHub App name**: choose a unique name (e.g. `my-oopsie`)
   - **Description**: optional — users see this when installing
   - **Homepage URL**: your Oopsie instance URL (e.g. `http://localhost:8000`)
3. Under **Identifying and authorizing users**:
   - **Callback URL**: leave blank (Oopsie does not use GitHub user-level OAuth)
   - **Setup URL**: `http://<your-host>/github/callback` (GitHub redirects here after a user installs the app)
   - Check **Redirect on update** so re-installations also redirect back
4. Under **Post installation**:
   - Leave defaults
5. Under **Webhook**:
   - Check **Active**
   - **Webhook URL**: `http://<your-host>/webhooks/github`
   - **Webhook secret**: generate a random secret — you'll need this for `GITHUB_WEBHOOK_SECRET`:
     ```bash
     python -c 'import secrets; print(secrets.token_urlsafe(32))'
     ```
6. Under **Permissions**, grant:
   - **Repository permissions**:
     - **Contents**: Read & write (clone repo, push fix branch)
     - **Pull requests**: Read & write (open fix PRs)
     - **Metadata**: Read-only (required by GitHub)
   - After setting permissions, the **Subscribe to events** checkboxes appear below — check **Pull request**
7. Set **Where can this GitHub App be installed?** to **Any account** (or **Only on this account** for private use)
8. Click **Create GitHub App**

**Configure credentials**

After creation, from the app's settings page:

- Copy the **App ID** (shown near the top) → `GITHUB_APP_ID`
- Scroll to **Private keys** → click **Generate a private key** → a `.pem` file downloads
- Base64-encode it for use as an env var:
  ```bash
  base64 -i path/to/your-app.YYYY-MM-DD.private-key.pem | tr -d '\n'
  ```
  Paste the output as `GITHUB_APP_PRIVATE_KEY_PEM`
- Copy the webhook secret you generated earlier → `GITHUB_WEBHOOK_SECRET`
- The **App slug** is the URL-safe name visible at `https://github.com/apps/<slug>` → `GITHUB_APP_SLUG`

Set all four values in your `.env` file.

### 5. Start services and run

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

```bash
make test             # starts test DB + runs pytest with coverage
```

Tests use a separate PostgreSQL instance on port 5434 (started automatically by `make test`).

### Linting & Type Checking

```bash
make lint             # ruff + mypy + bandit
```

### Full CI Check

Run the same checks as CI before pushing:

```bash
make ci               # lint + test in one command
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
| `SIGNING_SECRET` | Yes | Secret for signing cookies and CSRF tokens. Generate with: `python -c 'import secrets; print(secrets.token_urlsafe(32))'` |
| `ENCRYPTION_KEY` | Yes | Fernet key for encrypting GitHub tokens |
| `JWT_SECRET_KEY` | Yes | At least 32-char secret for signing JWTs |
| `GOOGLE_CLIENT_ID` | Yes | Google OAuth 2.0 client ID |
| `GOOGLE_CLIENT_SECRET` | Yes | Google OAuth 2.0 client secret |
| `ANTHROPIC_API_KEY` | For AI fixes | Claude API key for generating fix PRs |
| `GITHUB_APP_ID` | For GitHub integration | Numeric App ID from the GitHub App settings page |
| `GITHUB_APP_PRIVATE_KEY_PEM` | For GitHub integration | RSA private key, base64-encoded (see [GitHub App Setup](#4-set-up-the-github-app)) |
| `GITHUB_WEBHOOK_SECRET` | For GitHub integration | Webhook secret set in the GitHub App settings |
| `GITHUB_APP_SLUG` | For GitHub integration | App slug from `github.com/apps/{slug}` |
| `ADMIN_EMAIL` | First deploy | Email to seed the first OWNER invitation |
| `ORG_NAME` | No | Name for bootstrapped org (default: `"Oopsie"`) |
| `TEST_DATABASE_URL` | No | Defaults to `DATABASE_URL` with db name `oopsie_test` |
| `LOG_LEVEL` | No | Default: `INFO` |
| `LOG_FORMAT` | No | `json` (default) or `console` |

## License

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE).
