# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Web authentication migrated from JWT tokens to Redis-backed server-side sessions with 7-day sliding window TTL; instant session revocation on logout replaces the unbounded revoked_tokens table
- Auth flow migrated from JWT tokens to Redis-backed sessions. Login now creates a server-side session with a 7-day sliding window TTL instead of issuing JWT access/refresh token pairs. The `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_ACCESS_EXPIRY_MINUTES`, and `JWT_REFRESH_EXPIRY_MINUTES` environment variables are no longer used.
- Anthropic API key is now stored encrypted per-organization and per-project instead of as a global environment variable. Projects inherit the org key unless overridden. The `ANTHROPIC_API_KEY` environment variable is no longer used.

### Removed
- JWT token refresh middleware (TokenRefreshMiddleware) and POST /auth/refresh endpoint
- JWT_SECRET_KEY environment variable (no longer required)
- revoked_tokens database table (replaced by Redis session expiry)
- PyJWT dependency
- JWT-based authentication (access/refresh tokens, token rotation, token revocation)
- `TokenRefreshMiddleware` — no longer needed with server-side sessions
- `RevokedToken` model and `revoked_tokens` database table
- `pyjwt[crypto]` dependency
- `/auth/refresh` endpoint
- Bearer token header fallback for web auth (API key auth via Bearer header is unchanged)

### Fixed
- Fix pipeline now skips gracefully when no Anthropic API key is configured instead of crashing the worker
- Corrupted or re-keyed encrypted Anthropic keys no longer cause 500 errors (returns None with structured error log)
- Settings page raises 404 instead of silently swallowing missing organization

### Added
- Server-side token refresh middleware — users stay logged in for up to 7 days of inactivity instead of being logged out after 60 minutes (#21)
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

### Changed
- Extracted shared cookie constants (`AUTH_COOKIE_OPTS`) from `auth_routes.py` to `auth.py` for DRY reuse
