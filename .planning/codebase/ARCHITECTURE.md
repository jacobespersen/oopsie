# Architecture

**Analysis Date:** 2026-03-13

## Pattern Overview

**Overall:** Layered monolith with service-oriented business logic and dedicated worker process for background jobs.

**Key Characteristics:**
- **Request-response with async/await** — All endpoints and services are async; uses `AsyncSession` for database operations
- **Service layer encapsulation** — Business logic is isolated in `services/` modules; endpoints remain thin orchestrators
- **Dependency injection via FastAPI** — `Depends()` for session retrieval, auth, role-based access control (RBAC)
- **Worker queuing via arq/Redis** — Background jobs (fix pipeline) are enqueued and processed asynchronously
- **Multi-tenant organization model** — All data is scoped to organizations; users gain access via role-based memberships
- **Invitation-gated registration** — New users can only sign up if a pending invitation exists for their email

## Layers

**Presentation (Web/API):**
- Purpose: HTTP endpoints and HTML template responses
- Location: `oopsie/web/` (Jinja2 HTML forms), `oopsie/api/` (REST endpoints), `oopsie/auth_routes.py` (auth flows)
- Contains: Route handlers, form handling, response marshalling
- Depends on: Services, models, deps for DI
- Used by: Browser clients (web UI), SDK clients (error API)

**Application (API):**
- Purpose: REST endpoints for error ingestion and background job triggering
- Location: `oopsie/api/errors.py`
- Contains: `/api/v1/errors` POST endpoint for receiving error reports
- Depends on: Services, project authentication
- Used by: Client SDKs, error reporting libraries

**Service (Business Logic):**
- Purpose: Core domain logic and orchestration
- Location: `oopsie/services/`
- Contains:
  - `error_service.py` — Error ingestion, deduplication by fingerprint, occurrence tracking
  - `fix_service.py` — Fix attempt creation, status updates
  - `pipeline_service.py` — Orchestration of entire fix workflow (clone, generate, commit, PR)
  - `github_service.py` — GitHub operations (clone, branch, commit, push, PR creation)
  - `github_app_service.py` — GitHub App authentication, JWT generation, token exchange
  - `github_installation_service.py` — GitHub App installation tracking and repo listing
  - `membership_service.py` — User membership management, role enforcement
  - `invitation_service.py` — Invitation creation and management
  - `bootstrap_service.py` — First-deploy initialization
  - `claude_service.py` — Claude API integration for code generation
- Depends on: Models, database, external services (GitHub, Claude, Redis)
- Used by: Routes, workers

**Data (Models):**
- Purpose: SQLAlchemy ORM models with domain semantics
- Location: `oopsie/models/`
- Contains:
  - `base.py` — `DeclarativeBase` for all models
  - `user.py` — User (from Google OAuth)
  - `organization.py` — Organization (tenant boundary)
  - `membership.py` — User-Organization join with role hierarchy
  - `invitation.py` — Email-based invitations for new org members
  - `project.py` — GitHub repo project (belongs to org, has error reporting)
  - `error.py` — Deduplicated error (fingerprinted by class + message + stack)
  - `error_occurrence.py` — Individual occurrence record
  - `fix_attempt.py` — Attempt to generate and commit a fix
  - `github_installation.py` — GitHub App installation for an organization
  - `revoked_token.py` — Deny list for JWT token revocation
- Used by: Services, repositories

**Infrastructure:**
- Purpose: Cross-cutting concerns and external integrations
- Location: `oopsie/database.py`, `oopsie/config.py`, `oopsie/logging.py`, `oopsie/queue.py`, `oopsie/deps.py`, `oopsie/auth.py`
- Contains:
  - Database engine, session factory, async context managers
  - Pydantic settings (environment config with validation)
  - Structured logging (structlog + stdlib)
  - Redis/arq job queue
  - FastAPI dependency resolution
  - JWT authentication and Google OAuth

**Worker:**
- Purpose: Background job processing
- Location: `oopsie/worker/`
- Contains: Arq job entry point that delegates to `pipeline_service`
- Runs in: Separate process/container from web server

## Data Flow

**Error Ingestion:**

1. Client sends `POST /api/v1/errors` with error details (class, message, stack trace)
2. `oopsie/api/errors.py` endpoint handler validates auth via `get_project_from_api_key`
3. Calls `error_service.upsert_error()` to find or create Error by fingerprint
4. Increments occurrence count if duplicate, creates new ErrorOccurrence record
5. Returns 202 Accepted immediately
6. If error is new and meets threshold, enqueues fix job to Redis queue

**Fix Pipeline (Background Worker):**

1. Arq worker receives `run_fix_pipeline(error_id, project_id)` from queue
2. `oopsie/worker/fix_pipeline.py` delegates to `pipeline_service.run()`
3. `pipeline_service._load_and_prepare()` validates error, project, and GitHub installation
4. Creates PENDING `FixAttempt` record in database
5. `pipeline_service._run_fix()` orchestrates:
   - Get GitHub App installation token from `github_app_service`
   - Clone repo, create branch via `github_service`
   - Run Claude Code via `claude_service` (generates fixes)
   - Commit and push to branch
   - Create PR with Claude's output
6. On success: marks `FixAttempt` as SUCCESS, stores PR URL
7. On failure: marks `FixAttempt` as FAILED, stores error details
8. Cleans up temporary clone directory

**Web UI Navigation:**

1. User logs in via Google OAuth → `auth_routes.py` callback
2. `auth.resolve_or_register_user()` checks for pending invitations, accepts them
3. User redirected to first org's project list (`/orgs/{org_slug}/projects`)
4. Web routes in `oopsie/web/projects.py`, `oopsie/web/members.py`, etc. render Jinja2 templates
5. Form submissions trigger create/update/delete actions; redirects to list pages

**State Management:**

- **Database as source of truth** — All mutable state lives in PostgreSQL
- **Session-per-request in web** — FastAPI injects `get_session` dependency; middleware commits on success, rolls back on error
- **Session-per-job in worker** — `worker_session()` context manager wraps each background job
- **JWT in cookies** — Short-lived access token (60 min) + long-lived refresh token (7 days)
- **No in-process cache** — Services query database on each request (N+1 prevention via `selectinload()` / `joinedload()`)

## Key Abstractions

**Project:**
- Purpose: Represents a GitHub repository linked to an organization
- Examples: `oopsie/models/project.py`, `oopsie/web/projects.py`
- Pattern: Belongs to organization; contains errors and fix attempts; stores API key hash (never plain key)
- API key is hashed and matched via `get_project_from_api_key` dependency

**Error (Fingerprinted Deduplication):**
- Purpose: Deduplicated error record scoped to a project
- Examples: `oopsie/models/error.py`, `oopsie/services/error_service.py`
- Pattern: Fingerprint is deterministic hash of `error_class + message + stack_trace` (via `utils/fingerprint.py`)
- Multiple identical errors increment `occurrence_count` and update `last_seen_at`
- Status transitions: OPEN → FIX_ATTEMPTED → FIX_MERGED or IGNORED

**Membership (Role-Based Access Control):**
- Purpose: Binds user to organization with a role (MEMBER, ADMIN, OWNER)
- Examples: `oopsie/models/membership.py`, `oopsie/deps.py`
- Pattern: `RequireRole(MemberRole.admin)` dependency enforces minimum role on web routes
- Role hierarchy: MEMBER < ADMIN < OWNER (checked via `role_rank()`)

**Fix Attempt:**
- Purpose: Tracks a single attempt to generate and commit a fix
- Examples: `oopsie/models/fix_attempt.py`, `oopsie/services/fix_service.py`
- Pattern: Status lifecycle: PENDING → RUNNING → SUCCESS/FAILED
- Stores PR URL on success, error output on failure; de-duplication prevents duplicate pipeline runs

**GitHub Installation:**
- Purpose: Records GitHub App installation for an organization
- Examples: `oopsie/models/github_installation.py`, `oopsie/services/github_installation_service.py`
- Pattern: One per org; tracks installation ID, status, and GitHub user profile
- Used to exchange GitHub JWT for short-lived installation access tokens

## Entry Points

**Web Server (Uvicorn):**
- Location: `oopsie/main.py`
- Triggers: `uvicorn oopsie.main:app --reload` or container startup
- Responsibilities:
  - Creates FastAPI app with middleware stack
  - Mounts routers for auth (`/auth`), errors API (`/api/v1/errors`), and web UI (`/orgs/`)
  - Runs bootstrap on startup (seed first org/invitation if `ADMIN_EMAIL` set)
  - Handles lifespan cleanup (close Redis pool on shutdown)

**Background Worker (Arq):**
- Location: `oopsie/worker/fix_pipeline.py`, `Dockerfile.worker`
- Triggers: `arq oopsie.worker.settings.WorkerSettings` or container startup
- Responsibilities:
  - Listen on Redis queue for `run_fix_pipeline` jobs
  - Process jobs serially (controlled by `worker_concurrency` setting)
  - Execute fix pipeline orchestration
  - Update database with results

**API Error Ingestion:**
- Location: `oopsie/api/errors.py`
- Triggers: Client SDKs send `POST /api/v1/errors` with Bearer token (API key)
- Responsibilities:
  - Validate API key against project
  - Deduplicate and record error
  - Enqueue fix pipeline job if criteria met

**Google OAuth Callback:**
- Location: `oopsie/auth_routes.py` `/auth/callback`
- Triggers: User completes Google consent screen
- Responsibilities:
  - Exchange authorization code for user info
  - Check for pending invitations (invitation-gated registration)
  - Create or update user record
  - Accept invitations to become memberships
  - Issue JWT tokens, set cookies

## Error Handling

**Strategy:** Errors bubble up from services, caught at route level, mapped to HTTP responses.

**Patterns:**

- **Validation errors** → 400 Bad Request (Pydantic, custom HTTPException)
- **Auth failures** → 401 Unauthorized (missing/invalid/revoked JWT or API key)
- **Permission errors** → 403 Forbidden (user not member of org or insufficient role)
- **Not found** → 404 Not Found (project, error, org not found)
- **Background job failures** → Logged, FixAttempt marked FAILED with error details (not surfaced to user as HTTP error)
- **Database errors** → Logged as `db_session_rollback`, error propagates (500 Internal Server Error)
- **GitHub API errors** → Caught in `pipeline_service`, logged, FixAttempt marked FAILED

Services call `session.flush()` to surface database constraint violations early; endpoint middleware handles final commit/rollback.

## Cross-Cutting Concerns

**Logging:** Structured logging via `structlog` + stdlib. Every log line includes `request_id` (from middleware), event name (snake_case), and key-value context. Example: `logger.info("project_created", project_id=..., name=...)`.

**Validation:** Pydantic models for API request/response schemas. SQLAlchemy models enforce constraints. Settings validator ensures required env vars and valid encryption keys on startup.

**Authentication:** JWT in cookies (web) or Authorization header (Bearer token). Web auth checks `access_token` cookie or header. API auth checks Bearer token against hashed API keys. Both verify token is not revoked.

**Authorization:** RBAC via `RequireRole()` dependency. Extracts org membership from path (`org_slug`), enforces minimum role. Errors result in 403 Forbidden.

**Database:** Async SQLAlchemy with asyncpg driver. All models use UUID primary keys and timezone-aware timestamps. Relationships use `selectinload()` / `joinedload()` to prevent N+1 queries.

---

*Architecture analysis: 2026-03-13*
