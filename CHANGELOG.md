# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Web authentication migrated from JWT tokens to Redis-backed server-side sessions with 7-day sliding window TTL; instant session revocation on logout replaces the unbounded `revoked_tokens` table
- Anthropic API key is now stored encrypted per-organization and per-project instead of as a global environment variable. Projects inherit the org key unless overridden. The `ANTHROPIC_API_KEY` environment variable is no longer used.
- Login flow optimized from 7 DB round-trips to 4: existing users skip invitation lookup, memberships eagerly loaded with user query, org-scoped pages use single combined user+membership query via `get_authenticated_membership`
- DB connection pool tuned for Neon Postgres (pool_pre_ping, LIFO reuse, 5-min recycle)

### Removed
- JWT-based authentication (access/refresh tokens, token rotation, token revocation) — replaced by Redis sessions
- `TokenRefreshMiddleware` and `POST /auth/refresh` endpoint
- `RevokedToken` model and `revoked_tokens` database table
- `pyjwt[crypto]` dependency
- `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_ACCESS_EXPIRY_MINUTES`, `JWT_REFRESH_EXPIRY_MINUTES` environment variables
- Bearer token header fallback for web auth (API key auth via Bearer header is unchanged)

### Fixed
- Fix pipeline now skips gracefully when no Anthropic API key is configured instead of crashing the worker
- Corrupted or re-keyed encrypted Anthropic keys no longer cause 500 errors (returns None with structured error log)
- Settings page raises 404 instead of silently swallowing missing organization

### Added
- Audit logging for Anthropic key set/clear operations
- Fix pipeline now authenticates git operations with GitHub App installation access tokens; pipeline skips gracefully when no active installation exists for the project's org (PIPE-01)
- GitHub App installation flow: "Connect GitHub" redirect and OAuth callback per org (INST-01, INST-02)
- Org settings page at `/orgs/{slug}/settings` consolidating GitHub connection status and member management; `/members` GET redirects to `/settings` (INST-04)
- Webhook endpoint at `POST /webhooks/github` with HMAC-SHA256 signature verification (WHOOK-01)
- Webhook handlers for `installation.deleted`, `installation.suspended`, `installation.unsuspended` events (WHOOK-02, WHOOK-03)
- Webhook handler for `pull_request` closed+merged event — auto-updates fix attempt status to MERGED (WHOOK-04)
- Repo picker in project creation: dropdown from GitHub App installation repos replaces free-text URL input; access verified server-side (REPO-01, REPO-02)
- `FixAttemptStatus.MERGED` terminal status for PR-merged fix attempts
- `GITHUB_APP_SLUG` environment variable for constructing install redirect URLs
- GitHub App authentication service (`github_app_service.py`) with JWT client management, installation token exchange, webhook signature verification, and repo listing
- Error ingestion API with fingerprint-based deduplication
- Web dashboard for viewing projects, errors, and team members
- Background worker for automated fix generation using Claude Code
- Google OAuth authentication with invitation-gated registration
- Multi-tenant organization support with role-based access control
- GitHub token encryption at rest (Fernet)
- API key management with hash-based storage
- Structured JSON logging with structlog
