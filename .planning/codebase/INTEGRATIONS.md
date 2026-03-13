# External Integrations

**Analysis Date:** 2026-03-13

## APIs & External Services

**Google OAuth:**
- Service: Google Cloud Identity Platform (OpenID Connect)
- What it's used for: User authentication via Google account
- SDK/Client: authlib (`authlib[auth]` dependency)
- Auth: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` environment variables
- Implementation: `oopsie.auth.get_google_oauth_client()` builds cached OAuth client; `/auth/google/callback` endpoint in `oopsie.auth_routes.py`
- Flow: User logs in with Google → OAuth callback → JWT token issued → stored in `access_token` cookie

**GitHub App:**
- Service: GitHub App REST API + Webhooks
- What it's used for: Clone repos, list accessible repos, verify webhook signatures, create branches and PRs
- SDK/Client: githubkit (`githubkit[auth-app]` dependency)
- Auth: `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY_PEM` (base64-encoded), `GITHUB_WEBHOOK_SECRET` environment variables
- Implementation: `oopsie.services.github_app_service` provides:
  - `get_app_client()` - Singleton GitHub client authenticated as the app
  - `get_installation_client(installation_id)` - Per-request installation-scoped client
  - `get_installation_token()` - Exchange app JWT for short-lived installation access token (1 hour)
  - `list_installation_repos()` - List repos accessible to an installation
  - `verify_webhook()` - HMAC-SHA256 signature verification
- Webhook endpoint: `POST /github/webhook` in `oopsie.web.github`
- Usage: Cloning repos during fix pipeline, listing repos in settings UI, receiving installation events

**Anthropic Claude:**
- Service: Claude Code CLI subprocess
- What it's used for: AI-powered bug fixing via analysis of error and codebase
- SDK/Client: Claude Code CLI (`@anthropic-ai/claude-code` npm package)
- Auth: `ANTHROPIC_API_KEY` environment variable (passed to subprocess)
- Implementation: `oopsie.services.claude_service.run_claude_code()` spawns async subprocess:
  - Builds prompt from error class, message, and stack trace
  - Runs: `claude --print --dangerously-skip-permissions -p <prompt>`
  - Timeout: Configurable via settings (default: 600 seconds)
  - Raises `ClaudeCodeError` on failure or timeout
- Usage: Background worker job `run_fix_pipeline` in `oopsie.worker.fix_pipeline` invokes this during error fix attempt

## Data Storage

**Databases:**
- PostgreSQL 16 (async)
  - Connection: `database_url` environment variable (format: `postgresql+asyncpg://user:pass@host:port/dbname`)
  - Client: SQLAlchemy 2.0 async ORM with asyncpg driver
  - Schema: 8+ migrations in `alembic/versions/` covering:
    - Users, Organizations, Memberships, Invitations
    - Projects, Errors, ErrorOccurrences
    - FixAttempts, GithubInstallations
    - RevokedTokens (JWT deny list)
  - All models use UUID primary keys and timezone-aware timestamps
  - Async session factory: `oopsie.database.async_session_factory` (expire_on_commit=False, autoflush=False)

**File Storage:**
- Local filesystem only
  - Clone base path: `clone_base_path` setting (default: `/tmp/oopsie-clones`)
  - Worker clones repos here during fix pipeline execution

**Caching:**
- Redis 7 (async via arq)
  - Connection: `redis_url` environment variable (format: `redis://host:port`)
  - Purpose: Task queue backing for arq job processor
  - Used by: `oopsie.queue.get_arq_pool()` creates lazy singleton connection pool
  - Jobs: `run_fix_pipeline(error_id, project_id)` defined in `oopsie.worker.fix_pipeline`

## Authentication & Identity

**Auth Provider:**
- Dual auth strategy:
  1. Web: Google OAuth 2.0 (OpenID Connect) → JWT in `access_token` cookie
  2. API: Bearer token (API key) → hashed lookup via `get_project_from_api_key` dependency

**Implementation:**
- JWT: `oopsie.auth.create_access_token()` / `create_refresh_token()` - HS256 signed, configurable expiry
- Revocation: `RevokedToken` table tracks JTI claims for token deny list
- Dependencies:
  - `oopsie.deps.get_current_user` - Extracts user from JWT cookie
  - `oopsie.deps.get_project_from_api_key` - Looks up project via API key
  - `oopsie.deps.RequireRole` - RBAC enforcer (MEMBER < ADMIN < OWNER hierarchy)

**Invitation-Gated Registration:**
- New users can only sign up via Google OAuth if a pending `Invitation` exists for their email
- Existing users bypass the invitation check
- Implemented in `oopsie.auth.resolve_or_register_user()`

## Monitoring & Observability

**Error Tracking:**
- None detected (no Sentry, Rollbar, etc.)
- Errors logged to structured logs

**Logs:**
- Approach: Structured JSON logging via structlog
- Setup: `oopsie.logging.setup_logging(log_level, log_format)`
- Format options: `json` (default) or `console` (pretty-printed)
- Environment: `LOG_LEVEL` (default: INFO), `LOG_FORMAT` settings
- Request logging middleware: `oopsie.logging.RequestLoggingMiddleware` logs all requests
- Sample events: `user_created`, `token_revoked`, `fix_job_enqueued`, `github_app_client_initialized`, etc.

## CI/CD & Deployment

**Hosting:**
- Agnostic (Docker-based, suitable for any container platform)
- Entrypoint: `docker-entrypoint.sh` runs migrations and starts Uvicorn

**CI Pipeline:**
- GitHub Actions (`.github/workflows/ci.yml`)
- Runs on: Push to main, pull requests to main
- Python 3.11, PostgreSQL 16 service container
- Steps:
  1. Ruff lint + format check
  2. MyPy type check
  3. Bandit security scan
  4. pip-audit dependency audit
  5. pytest with 90% coverage floor

## Environment Configuration

**Required env vars:**
- `DATABASE_URL` - Async PostgreSQL connection string
- `REDIS_URL` - Redis connection string

**Conditional Required:**
- `JWT_SECRET_KEY` - Required if `GOOGLE_CLIENT_ID` is set (minimum 32 characters)
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` - Both required for OAuth login
- `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY_PEM`, `GITHUB_WEBHOOK_SECRET` - All three required for GitHub App integration; warning if partial

**Optional:**
- `ENCRYPTION_KEY` - Fernet key for encrypting sensitive data (GitHub tokens); warning if not set
- `ANTHROPIC_API_KEY` - Claude API key (blank = Claude features disabled)
- `TEST_DATABASE_URL` - Test DB URL (defaults to `database_url` with db name `oopsie_test`)
- `LOG_LEVEL` - Default: INFO
- `LOG_FORMAT` - Default: json
- `ADMIN_EMAIL` - Email for bootstrap OWNER invitation on first deploy
- `ORG_NAME` - Organization name for bootstrap (default: "Default")
- `GITHUB_APP_SLUG` - Human-readable GitHub App slug (from `github.com/apps/{slug}`)
- `COOKIE_SECURE` - Set to true in production (default: false for dev)
- `WORKER_CONCURRENCY` - arq worker concurrency (default: 3)
- `JOB_TIMEOUT_SECONDS` - arq job timeout (default: 600)
- `CLONE_BASE_PATH` - Base directory for cloning repos (default: `/tmp/oopsie-clones`)

**Secrets location:**
- Environment variables (`.env` file, sourced via pydantic-settings)
- GitHub App private key: base64-encoded PEM in `GITHUB_APP_PRIVATE_KEY_PEM`
- Encryption key: Fernet-generated key in `ENCRYPTION_KEY`
- Validation: `oopsie.config.Settings` validates all keys on instantiation

## Webhooks & Callbacks

**Incoming:**
- GitHub App Webhook: `POST /github/webhook`
  - Payload: Installation events (created, deleted, etc.), repository events
  - Handler: `oopsie.web.github.receive_webhook()` verifies signature via `github_app_service.verify_webhook()`
  - Stores: `GithubInstallation` record on successful verification

**Outgoing:**
- None detected (no external webhooks triggered by Oopsie)

---

*Integration audit: 2026-03-13*
