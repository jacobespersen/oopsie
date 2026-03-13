# Technology Stack

**Analysis Date:** 2026-03-13

## Languages

**Primary:**
- Python 3.11+ - FastAPI backend, worker, CLI automation
- HTML/Jinja2 - Web UI templates
- JavaScript - Claude Code CLI (Node.js)

**Secondary:**
- SQL - PostgreSQL queries (via SQLAlchemy)

## Runtime

**Environment:**
- Python 3.11 (docker image: `python:3.11-slim`)
- Node.js 20.x (for Claude Code CLI in worker container)

**Package Manager:**
- pip - Python dependency management
- npm - Node.js package management (Claude Code)
- Lockfile: `pyproject.toml` with setuptools build system

## Frameworks

**Core:**
- FastAPI 0.x - Web API framework and routing
- Uvicorn 0.x - ASGI server (runs on `0.0.0.0:8000`)
- Jinja2 - HTML template rendering for web UI

**Database:**
- SQLAlchemy 2.0 - Async ORM with declarative models (`Mapped[]`, `mapped_column()`)
- asyncpg - Async PostgreSQL driver
- Alembic - Database schema migrations

**Task Queue:**
- arq - Redis-backed async task queue
- Redis 7-alpine - Message broker and job storage

**Testing:**
- pytest - Test runner with `asyncio_mode = "auto"`
- pytest-asyncio - Async test support
- pytest-cov - Coverage reporting (threshold: 90%)
- factory-boy 3.3+ - Test data factories

**Build/Dev:**
- ruff - Linting and formatting (line-length: 88, Python 3.11+)
- mypy - Static type checking (warn_return_any, warn_unused_ignores)
- bandit - Security scanning (skips B101 for pytest asserts)
- pre-commit - Git hooks framework
- honcho - Foreman-like process manager

## Key Dependencies

**Critical:**
- pydantic-settings - Configuration management via environment variables
- python-multipart - Form data parsing for FastAPI
- authlib[auth] - OAuth 2.0 integrations
- PyJWT[crypto] - JWT token creation/verification
- githubkit[auth-app] - GitHub App authentication and REST API client
- cryptography - Fernet encryption for sensitive data (GitHub tokens)

**Infrastructure:**
- httpx - Async HTTP client (implicitly via authlib/githubkit)
- itsdangerous - Token signing utilities
- greenlet - Async concurrency support for SQLAlchemy
- psycopg2-binary - PostgreSQL client (fallback connector)
- redis[hiredis] - Redis client with C acceleration
- structlog - Structured JSON logging

## Configuration

**Environment:**
- Configuration source: `.env` file via pydantic-settings
- Settings class: `oopsie.config.Settings` (cached via `@lru_cache`)
- Required settings: `database_url`, `redis_url` (fail-loud if missing)
- Optional settings: encryption key, JWT secret, Google OAuth credentials, GitHub App credentials, Anthropic API key

**Build:**
- `pyproject.toml` - Project metadata, dependencies, tool configuration
- `Dockerfile` - Multi-stage build (builder + runtime)
- `Dockerfile.worker` - Worker process image (includes Node.js for Claude Code)
- `docker-compose.yml` - Dev/test containers (PostgreSQL dev, PostgreSQL test, Redis)
- `alembic.ini` - Database migration configuration

**Linting Configuration:**
- Ruff: `[tool.ruff]` in `pyproject.toml` with E, F, I, N, W, UP rules enabled
- MyPy: Python 3.11 target, warn on return any and unused ignores
- Bandit: Excludes test directory, skips B101

## Platform Requirements

**Development:**
- Python 3.11+
- Docker (for PostgreSQL 16 and Redis)
- PostgreSQL 16 on `localhost:5433` for dev
- PostgreSQL 16 on `localhost:5434` for tests (profile: `test`)
- Redis 7 on `localhost:6379` (profile: `redis`)
- Git (for GitHub operations)
- Node.js 20.x (worker container only)
- Claude Code CLI installed globally (worker container: `npm install -g @anthropic-ai/claude-code`)

**Production:**
- Python 3.11 runtime
- PostgreSQL 16+ database
- Redis 7+ message broker
- Node.js 20+ (for Claude Code execution in worker processes)
- Docker or container orchestration (Kubernetes, ECS, etc.)
- Environment variables: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, `ENCRYPTION_KEY`, plus optional OAuth/GitHub App credentials

---

*Stack analysis: 2026-03-13*
