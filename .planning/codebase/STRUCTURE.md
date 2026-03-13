# Codebase Structure

**Analysis Date:** 2026-03-13

## Directory Layout

```
oopsie/
├── oopsie/                          # Main package
│   ├── main.py                      # FastAPI app entry point, middleware, router registration
│   ├── config.py                    # Pydantic settings (env vars, validation)
│   ├── database.py                  # AsyncSession factory, engine setup
│   ├── logging.py                   # structlog configuration, RequestLoggingMiddleware
│   ├── auth.py                      # JWT, Google OAuth, user registration logic
│   ├── auth_routes.py               # /auth/* endpoints (login, callback, logout, refresh)
│   ├── deps.py                      # FastAPI dependencies (get_session, auth, RBAC)
│   ├── queue.py                     # Redis/arq pool management
│   ├── api/                         # REST API endpoints
│   │   ├── __init__.py
│   │   └── errors.py                # POST /api/v1/errors (error ingestion)
│   ├── models/                      # SQLAlchemy ORM models
│   │   ├── __init__.py              # Exports all models
│   │   ├── base.py                  # DeclarativeBase
│   │   ├── user.py                  # User (from Google OAuth)
│   │   ├── organization.py          # Organization (tenant)
│   │   ├── membership.py            # User-Org join with role
│   │   ├── invitation.py            # Email-based invitation
│   │   ├── project.py               # GitHub repo project
│   │   ├── error.py                 # Deduplicated error
│   │   ├── error_occurrence.py      # Individual occurrence
│   │   ├── fix_attempt.py           # Fix attempt record
│   │   ├── github_installation.py   # GitHub App installation
│   │   └── revoked_token.py         # JWT revocation deny list
│   ├── services/                    # Business logic layer
│   │   ├── __init__.py
│   │   ├── error_service.py         # Error ingestion & deduplication
│   │   ├── fix_service.py           # Fix attempt CRUD
│   │   ├── pipeline_service.py      # Fix pipeline orchestration
│   │   ├── github_service.py        # Git operations (clone, push, etc)
│   │   ├── github_app_service.py    # GitHub App JWT & token exchange
│   │   ├── github_installation_service.py  # GitHub App install mgmt
│   │   ├── claude_service.py        # Claude Code integration
│   │   ├── membership_service.py    # Membership operations
│   │   ├── invitation_service.py    # Invitation operations
│   │   ├── bootstrap_service.py     # First-deploy setup
│   │   ├── exceptions.py            # Service-level exceptions
│   │   └── (other services)
│   ├── utils/                       # Shared utilities
│   │   ├── __init__.py
│   │   ├── encryption.py            # Fernet encryption for tokens
│   │   └── fingerprint.py           # Error fingerprinting (hash)
│   ├── web/                         # Web UI routes (Jinja2 HTML)
│   │   ├── __init__.py              # Jinja2Templates setup
│   │   ├── projects.py              # GET/POST /orgs/{org_slug}/projects/*
│   │   ├── errors.py                # GET /orgs/{org_slug}/projects/{id}/errors
│   │   ├── members.py               # GET/POST /orgs/{org_slug}/members*
│   │   ├── settings.py              # GET/POST /orgs/{org_slug}/settings*
│   │   └── github.py                # GET /github/* (GitHub App callbacks)
│   └── worker/                      # Background job processing
│       ├── __init__.py
│       ├── fix_pipeline.py          # Arq job entry point
│       └── settings.py              # Arq WorkerSettings config
├── templates/                       # Jinja2 HTML templates
│   ├── base.html                    # Base layout (nav, styles)
│   ├── auth/
│   │   └── login.html               # Login page with Google button
│   ├── projects/
│   │   ├── list.html                # Project listing
│   │   ├── form.html                # Create/edit project form
│   │   ├── api_key.html             # API key display & regeneration
│   │   └── errors.html              # Error list for project
│   ├── members/
│   │   ├── list.html                # Organization members
│   │   └── invite.html              # Invite new member form
│   └── settings/
│       └── github.html              # GitHub App installation status
├── static/                          # Static assets
│   └── css/                         # Stylesheets
├── alembic/                         # Database migrations
│   ├── env.py
│   ├── alembic.ini
│   └── versions/                    # Migration files
├── tests/                           # Test suite
│   ├── conftest.py                  # Shared fixtures (db_session, factories)
│   ├── factories.py                 # Factory-boy factories
│   ├── api/
│   │   └── test_*.py                # API endpoint tests
│   ├── services/
│   │   └── test_*.py                # Service tests
│   ├── models/
│   │   └── test_*.py                # Model tests
│   └── web/
│       └── test_*.py                # Web route tests
├── pyproject.toml                   # Python dependencies, tools config
├── Dockerfile                       # Web server image
├── Dockerfile.worker                # Background worker image
├── docker-compose.yml               # Local dev: postgres, redis
└── CLAUDE.md                        # Project conventions & guidelines
```

## Directory Purposes

**oopsie/:**
- Purpose: Main Python package containing all business logic and HTTP handlers
- Contains: Source code organized by concern (models, services, web, api)
- Key files: `main.py` (entry point), `config.py` (settings), `database.py` (ORM setup)

**oopsie/models/:**
- Purpose: SQLAlchemy ORM layer — defines database schema and relationships
- Contains: 11 model classes (User, Organization, Project, Error, etc.)
- Key files: `base.py` (DeclarativeBase), individual model files for each entity
- Pattern: All models use `uuid.uuid4` as primary key, timezone-aware timestamps

**oopsie/services/:**
- Purpose: Business logic isolated from HTTP handlers
- Contains: Stateless functions that query/modify models, orchestrate workflows
- Key files: `error_service.py` (ingestion), `pipeline_service.py` (orchestration), `github_*.py` (GitHub integration)
- Pattern: Services take `AsyncSession` as first parameter, call `session.flush()` before returning

**oopsie/api/:**
- Purpose: REST API endpoints for programmatic access (error ingestion)
- Contains: Single router for error ingestion
- Key files: `errors.py` (POST /api/v1/errors endpoint)
- Pattern: Thin handlers that validate input, call services, return Pydantic response models

**oopsie/web/:**
- Purpose: HTML routes for browser-based UI (project management, member management)
- Contains: Route handlers that return Jinja2 template responses or form redirects
- Key files: `projects.py`, `members.py`, `errors.py` (various GET/POST handlers)
- Pattern: Forms use POST with HTML redirects (no JavaScript); uses `RequireRole()` for RBAC

**oopsie/worker/:**
- Purpose: Background job processing — separate from web server
- Contains: Arq job entry point that delegates to services
- Key files: `fix_pipeline.py` (job handler), `settings.py` (Arq config)
- Pattern: Jobs are fire-and-forget; status updates are written to database by service

**templates/:**
- Purpose: Jinja2 HTML templates for web UI
- Contains: Base layout, page templates organized by feature (auth, projects, members, settings)
- Key files: `base.html` (navigation, common styles), feature-specific subdirectories
- Pattern: All templates inherit from `base.html`; form submissions POST to route handlers

**static/:**
- Purpose: CSS, JavaScript, images
- Contains: CSS only (no JavaScript in use yet)
- Key files: `css/` subdirectory for stylesheets
- Pattern: Mounted at `/static` via FastAPI `StaticFiles()`

**alembic/:**
- Purpose: Database schema migrations
- Contains: Versioned migration files auto-generated from model changes
- Key files: `env.py`, `versions/*.py`
- Pattern: Run `alembic revision --autogenerate -m "desc"` after model changes

**tests/:**
- Purpose: Test suite with pytest + async support
- Contains: Tests organized by layer (api, services, models, web)
- Key files: `conftest.py` (shared fixtures), `factories.py` (test data factories)
- Pattern: Factory-based test data creation; single `db_session` fixture for all tests

## Key File Locations

**Entry Points:**
- `oopsie/main.py`: Web server entry point; registers routers, sets up middleware
- `oopsie/worker/fix_pipeline.py`: Background worker entry point; Arq job handler
- `oopsie/auth_routes.py`: Authentication flow entry points (`/auth/login`, `/auth/callback`)

**Configuration:**
- `oopsie/config.py`: Pydantic settings (database_url, redis_url, api keys, etc.)
- `pyproject.toml`: Python dependencies, pytest/mypy/ruff config
- `alembic.ini`: Database migration config

**Core Logic:**
- `oopsie/services/error_service.py`: Error ingestion and deduplication
- `oopsie/services/pipeline_service.py`: End-to-end fix workflow (clone → Claude → PR)
- `oopsie/services/github_*.py`: GitHub integration (auth, repos, PRs)
- `oopsie/auth.py`: JWT creation, Google OAuth, user registration

**API & Web Routes:**
- `oopsie/api/errors.py`: REST endpoint for error reports (`POST /api/v1/errors`)
- `oopsie/web/projects.py`: CRUD endpoints for projects
- `oopsie/web/members.py`: Membership and invitation endpoints
- `oopsie/auth_routes.py`: Auth flow endpoints

**Testing:**
- `tests/conftest.py`: Shared pytest fixtures
- `tests/factories.py`: Factory-boy factories for test data
- `tests/api/`, `tests/services/`, `tests/web/`: Test files mirroring source structure

**Database & ORM:**
- `oopsie/database.py`: AsyncSession factory, engine setup
- `oopsie/models/`: SQLAlchemy models (11 files, one per entity)
- `alembic/versions/`: Migration files

## Naming Conventions

**Files:**
- Model files: `{entity}.py` (e.g., `user.py`, `project.py`)
- Service files: `{domain}_service.py` (e.g., `error_service.py`, `github_service.py`)
- Route files: `{feature}.py` (e.g., `projects.py`, `members.py`)
- Test files: `test_{feature}.py` (e.g., `test_errors.py`)

**Directories:**
- Plural nouns for module directories: `models/`, `services/`, `utils/`, `tests/`
- Feature-based subdirectories in `web/` and `templates/`: `auth/`, `projects/`, `members/`

**Functions & Classes:**
- Classes: PascalCase (e.g., `User`, `Organization`, `FixAttempt`, `ErrorStatus`)
- Functions: snake_case (e.g., `upsert_error`, `get_project_from_api_key`, `create_access_token`)
- Route handlers: snake_case with descriptive suffix (e.g., `list_projects_page`, `create_project_action`)
- Event log names: snake_case (e.g., `project_created`, `user_logged_in`, `error_deduplicated`)

**Database:**
- Tables: plural snake_case (e.g., `users`, `organizations`, `projects`, `errors`)
- Columns: snake_case (e.g., `project_id`, `created_at`, `github_repo_url`)
- Primary keys: `id` (UUID)
- Timestamps: `created_at`, `updated_at` (always timezone-aware)
- Foreign keys: `{entity}_id` (e.g., `project_id`, `organization_id`)

**API Routes:**
- Web routes: `/orgs/{org_slug}/...` (all org-scoped pages)
- API routes: `/api/v1/...` (versioned API endpoints)
- Auth routes: `/auth/...` (login, callback, logout, refresh)
- GitHub callbacks: `/github/...` (GitHub App webhooks)

## Where to Add New Code

**New Feature (End-to-End):**
1. **Model** — Add ORM class to `oopsie/models/{entity}.py`; run `alembic revision --autogenerate`
2. **Service** — Add business logic to `oopsie/services/{domain}_service.py`
3. **Route** — Add endpoint to `oopsie/web/{feature}.py` or `oopsie/api/` as appropriate
4. **Template** — Add Jinja2 template to `templates/{feature}/...` (only for web UI)
5. **Tests** — Add test file to `tests/{layer}/test_{feature}.py` matching the route/service

**New Component/Module:**
- If it's a domain service (error handling, member management): Add to `oopsie/services/` as `{domain}_service.py`
- If it's a shared utility (encryption, fingerprinting): Add to `oopsie/utils/` as `{concern}.py`
- If it's a set of related routes: Create or update a file in `oopsie/web/` or `oopsie/api/`

**Utilities:**
- Shared helpers: `oopsie/utils/` (keep functions simple and testable)
- Example: `oopsie/utils/fingerprint.py` handles error deduplication hashing; used by `error_service.py`

**New Background Job:**
- Add job function to `oopsie/worker/{job_name}.py`
- Register in Arq settings (`oopsie/worker/settings.py`)
- Call `queue.enqueue_job()` or `enqueue_*()` function from web/API layer
- Example: `run_fix_pipeline()` is already set up in `oopsie/worker/fix_pipeline.py`

## Special Directories

**alembic/versions/:**
- Purpose: Database schema versions
- Generated: Yes (via `alembic revision --autogenerate`)
- Committed: Yes (to version control)
- Pattern: One file per migration, numbered sequentially (e.g., `001_init_schema.py`)

**tests/:**
- Purpose: Test suite
- Generated: No (human-written)
- Committed: Yes (to version control)
- Pattern: Mirror source structure; factory-based test data; async test support via pytest-asyncio

**static/:**
- Purpose: CSS, JS, images served to browser
- Generated: No (CSS currently hand-written)
- Committed: Yes (to version control)
- Pattern: Organized by type (`css/`, `js/`, `images/`)

**.venv/:**
- Purpose: Python virtual environment
- Generated: Yes (via `make setup`)
- Committed: No (in `.gitignore`)

**migrations/ (temporary clones):**
- Purpose: Git repository clones for fix pipeline processing
- Generated: Yes (at runtime, in `/tmp/oopsie-clones/` by default)
- Committed: No (cleaned up after job completes)
- Pattern: Created with `tempfile.mkdtemp()`, removed by `shutil.rmtree()` in finally block

---

*Structure analysis: 2026-03-13*
