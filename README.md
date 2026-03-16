# Oopsie

[![CI](https://github.com/jacobespersen/oopsie/actions/workflows/ci.yml/badge.svg)](https://github.com/jacobespersen/oopsie/actions/workflows/ci.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

**[getoopsie.com](https://getoopsie.com)** — Hosted version, free to try.

Oopsie is a self-hosted error tracking service that automatically generates fix PRs using [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Point your application at Oopsie's API, and when errors exceed a configured threshold it clones your repo, diagnoses the issue, and opens a pull request with the fix.

> **Feature requests welcome!** Open an issue on [GitHub](https://github.com/jacobespersen/oopsie/issues) to suggest new features or improvements.

## How It Works

1. **Report** — Your app sends errors to Oopsie's ingestion API (deduplicated by fingerprint)
2. **Track** — Oopsie aggregates occurrences and surfaces errors in a web dashboard
3. **Fix** — When an error crosses the threshold, a background worker invokes Claude Code to analyze the stack trace, write a fix, and open a PR on GitHub

### Security: Claude Code Sandbox

When generating fixes, Oopsie clones your repository into a temporary directory and runs Claude Code against that clone using the [Claude Code SDK](https://docs.anthropic.com/en/docs/claude-code). Claude Code operates in a sandboxed environment scoped to the cloned repository — it cannot access the deployed Oopsie application, your database, or any other files on the host. The clone is cleaned up after the fix attempt completes.

## Client Libraries

| Language | Gem / Package | Description |
|----------|---------------|-------------|
| Ruby | [`oopsie-ruby`](https://github.com/jacobespersen/oopsie-ruby) | Lightweight gem with Rack middleware and manual reporting — zero runtime dependencies |

### Reporting Errors via HTTP

No client library required — you can report errors with a plain HTTP request:

```bash
curl -X POST https://getoopsie.com/api/v1/errors \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "error_class": "ZeroDivisionError",
    "message": "division by zero",
    "stack_trace": "app/models/calculator.rb:12:in `/'\'''\''napp/controllers/calc_controller.rb:8:in '\''compute'\''"
  }'
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `error_class` | string | Yes | Exception class name (e.g. `ZeroDivisionError`, `TypeError`) |
| `message` | string | Yes | Human-readable error message |
| `stack_trace` | string | No | Full stack trace / backtrace |

Returns `202 Accepted` on success. Errors with the same class and message are automatically deduplicated by fingerprint.

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
                        │ (storage) │        │  (sessions + │      │  (Jinja2)   │
                        └───────────┘        │   job queue) │      └─────────────┘
                                             └──────┬───────┘
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
# Signing secret for cookies and CSRF tokens
python -c 'import secrets; print(secrets.token_urlsafe(32))'

# Fernet key for encrypting GitHub tokens
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
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
4. The bootstrap user is automatically granted **platform admin** privileges (see [Platform Admin](#platform-admin) below)
5. Invite additional users from the **Settings** page

> Bootstrap only runs once and is a no-op if an organization already exists.

## Platform Admin

The `is_platform_admin` flag is a special privilege granted to the user whose email matches `ADMIN_EMAIL`. It is set automatically when that user first signs in via Google OAuth.

Platform admins have access to features that operate outside any single organization:

- **Signup request management** (`/admin/signup-requests`) — review, approve, or reject requests from users who want to create their own organization on the platform
- Approving a signup request creates an org-creation invitation, allowing the requester to sign in and set up their own organization

All other access control is org-scoped via role-based permissions (MEMBER, ADMIN, OWNER).

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
  main.py            — FastAPI app, middleware, router wiring
  config.py          — Pydantic Settings (reads .env)
  database.py        — Async SQLAlchemy engine + session factory
  auth.py            — Google OAuth, invitation gating, platform admin assignment
  session.py         — Redis-backed server-side session management
  routers/           — All endpoint definitions
    __init__.py      — Aggregates & re-exports all router instances
    dependencies.py  — Shared route deps (auth, RBAC, DI)
    auth.py          — /auth/* endpoints (login, callback, logout)
    github.py        — GitHub App install flow + webhooks
    api/
      errors.py      — REST API error ingestion endpoint
    web/
      landing.py     — Public landing page + signup request form
      projects.py    — Project CRUD
      errors.py      — Error listing, detail view, fix triggering
      members.py     — Member & invitation management
      settings.py    — Org settings (GitHub connection, Anthropic key)
      admin.py       — Platform admin: signup request management
  models/            — SQLAlchemy ORM models
  services/          — Business logic layer
  middleware/        — Request logging, org slug extraction
  utils/             — Encryption, fingerprinting, slug generation
  worker/            — Background job processing (arq + Claude Code SDK)
templates/           — Jinja2 templates
alembic/             — Database migrations
tests/               — Test suite (pytest, factory-boy)
```

## API Endpoints

### Ingestion API

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/errors` | Bearer token (API key) | Report an error (202 Accepted) |

### Authentication

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/auth/login` | Login page |
| `GET` | `/auth/login/google` | Redirect to Google OAuth |
| `GET` | `/auth/callback` | Google OAuth callback |
| `POST` | `/auth/logout` | Destroy session and redirect to login |

### Web UI (org-scoped: `/orgs/{org_slug}/...`)

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/orgs/{org_slug}/projects` | MEMBER | List projects |
| `GET` | `/orgs/{org_slug}/projects/new` | ADMIN | New project form |
| `POST` | `/orgs/{org_slug}/projects` | ADMIN | Create project |
| `GET` | `/orgs/{org_slug}/projects/{id}/edit` | ADMIN | Edit project form |
| `POST` | `/orgs/{org_slug}/projects/{id}` | ADMIN | Update project |
| `POST` | `/orgs/{org_slug}/projects/{id}/delete` | ADMIN | Delete project |
| `GET` | `/orgs/{org_slug}/projects/{id}/api-key` | ADMIN | View API key |
| `POST` | `/orgs/{org_slug}/projects/{id}/regenerate-api-key` | ADMIN | Regenerate API key |
| `GET` | `/orgs/{org_slug}/projects/{pid}/errors` | MEMBER | List errors |
| `GET` | `/orgs/{org_slug}/projects/{pid}/errors/{eid}` | MEMBER | Error detail |
| `POST` | `/orgs/{org_slug}/projects/{pid}/errors/{eid}/fix` | MEMBER | Trigger fix attempt |
| `GET` | `/orgs/{org_slug}/settings` | MEMBER | Org settings page |
| `POST` | `/orgs/{org_slug}/settings/anthropic-key` | ADMIN | Set/clear Anthropic API key |
| `POST` | `/orgs/{org_slug}/members/invite` | ADMIN | Send invitation |
| `POST` | `/orgs/{org_slug}/members/invitations/{id}/revoke` | ADMIN | Revoke invitation |
| `POST` | `/orgs/{org_slug}/members/{id}/role` | ADMIN | Change member role |
| `POST` | `/orgs/{org_slug}/members/{id}/remove` | ADMIN | Remove member |
| `GET` | `/orgs/{org_slug}/github/install` | ADMIN | Start GitHub App installation |
| `GET` | `/github/callback` | Authenticated | GitHub App install callback |

### GitHub Webhooks

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/webhooks/github` | HMAC signature | Receive GitHub webhook events |

### Platform Admin

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/admin/signup-requests` | Platform admin | List signup requests |
| `POST` | `/admin/signup-requests/{id}/approve` | Platform admin | Approve request |
| `POST` | `/admin/signup-requests/{id}/reject` | Platform admin | Reject request |

### Other

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Landing page (redirects authenticated users to projects) |
| `POST` | `/signup-request` | Submit signup request (public) |
| `GET` | `/health` | Health check |

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | Async PostgreSQL URL (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Yes | Redis connection URL (e.g. `redis://localhost:6379`) |
| `SIGNING_SECRET` | Yes | Secret for signing cookies and CSRF tokens. Generate with: `python -c 'import secrets; print(secrets.token_urlsafe(32))'` |
| `ENCRYPTION_KEY` | No | Fernet key for encrypting GitHub tokens (warned if missing) |
| `GOOGLE_CLIENT_ID` | For OAuth | Google OAuth 2.0 client ID |
| `GOOGLE_CLIENT_SECRET` | For OAuth | Google OAuth 2.0 client secret |
| `GITHUB_APP_ID` | For GitHub | Numeric App ID from the GitHub App settings page |
| `GITHUB_APP_PRIVATE_KEY_PEM` | For GitHub | RSA private key, base64-encoded (see [GitHub App Setup](#4-set-up-the-github-app)) |
| `GITHUB_WEBHOOK_SECRET` | For GitHub | Webhook secret set in the GitHub App settings |
| `GITHUB_APP_SLUG` | For GitHub | App slug from `github.com/apps/{slug}` |
| `ADMIN_EMAIL` | First deploy | Email to seed the first OWNER invitation + platform admin |
| `ORG_NAME` | No | Name for bootstrapped org (default: `"Default"`) |
| `COOKIE_SECURE` | No | Set `true` for HTTPS in production (default: `false`) |
| `WORKER_CONCURRENCY` | No | Max concurrent background jobs (default: `3`) |
| `JOB_TIMEOUT_SECONDS` | No | Timeout for Claude Code execution in seconds (default: `600`) |
| `CLONE_BASE_PATH` | No | Directory for temporary repo clones (default: system temp dir) |
| `TEST_DATABASE_URL` | No | Defaults to `DATABASE_URL` with db name `oopsie_test` |
| `LOG_LEVEL` | No | Default: `INFO` |
| `LOG_FORMAT` | No | `json` (default) or `console` |

## License

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE).
