# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Detached ORM object bug in `accept_org_creation_invitation` logging after invitation deletion
- Auth callback now catches only `NoInvitationError` instead of bare `ValueError`, allowing other exceptions to propagate
- Stale docstring in `require_platform_admin` referencing JWT verification instead of session verification
- `get_optional_user` now only catches 401 errors; other HTTP errors (500, etc.) propagate instead of being silently swallowed
- Invalid `status` query param on `/admin/signup-requests` now returns 400 instead of silently defaulting to "pending"
- `generate_unique_slug` loop is now bounded to `max_attempts=100` with warning logs on each collision retry and `RuntimeError` on exhaustion
- Admin approve/reject error handlers now log warnings with request ID and error details for `LookupError` and `ValueError` cases
- Row-level locking (`SELECT ... FOR UPDATE`) on approve/reject signup request to prevent race conditions
- IntegrityError handling on signup form submission to gracefully handle concurrent duplicate requests

### Added
- `SignupRequestForm` Pydantic model for server-side input validation (field length limits, email format)
- Frontend `maxlength` attributes on signup form inputs
- `UniqueConstraint` on `OrgCreationInvitation.signup_request_id` preventing duplicate invitations per request
- `CHECK` constraint on `SignupRequest` ensuring `reviewed_by_id`/`reviewed_at` consistency with status
- Alembic migration 010 for new database constraints

### Security
- CSRF double-submit cookie protection on all state-changing web requests via `starlette-csrf` middleware; API routes, `/signup-request`, and `/webhooks/github` are exempt

### Added
- Public landing page at `/` with signup request form for new organization onboarding (#17)
- `SignupRequest` model with partial unique index (one pending request per email, resubmission allowed after rejection)
- `OrgCreationInvitation` model — created when a platform admin approves a signup request, consumed on OAuth login
- Platform admin dashboard at `/admin/signup-requests` for reviewing, approving, and rejecting signup requests
- `is_platform_admin` flag on User model, auto-set during OAuth login when email matches `ADMIN_EMAIL`
- `require_platform_admin` FastAPI dependency for gating admin-only routes
- `slugify` and `generate_unique_slug` utilities extracted to `oopsie/utils/slug.py` with slug collision handling
- Auth flow (`resolve_or_register_user`) now handles org-creation invitations: creates org + OWNER membership on login
- Admin navigation link in site header (visible only to platform admins)

### Changed
- Web authentication migrated from JWT tokens to Redis-backed server-side sessions with 7-day sliding window TTL; instant session revocation on logout replaces the unbounded `revoked_tokens` table
- Anthropic API key is now stored encrypted per-organization and per-project instead of as a global environment variable. Projects inherit the org key unless overridden. The `ANTHROPIC_API_KEY` environment variable is no longer used.
- Replace Claude Code CLI subprocess with `claude-agent-sdk` Python SDK for cleaner process management and error handling

### Security
- Worker Docker container now runs as non-root `worker` user instead of root
- Login flow optimized from 7 DB round-trips to 4: existing users skip invitation lookup, memberships eagerly loaded with user query, org-scoped pages use single combined user+membership query via `get_authenticated_membership`
- DB connection pool uses LIFO reuse to reduce Neon cold starts
- OAuth callback returns a "Signing you in..." transition page instead of a blank redirect, with loading state on the sign-in button for immediate visual feedback

### Removed
- JWT-based authentication (access/refresh tokens, token rotation, token revocation) — replaced by Redis sessions
- `TokenRefreshMiddleware` and `POST /auth/refresh` endpoint
- `RevokedToken` model and `revoked_tokens` database table
- `pyjwt[crypto]` dependency
- `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_ACCESS_EXPIRY_MINUTES`, `JWT_REFRESH_EXPIRY_MINUTES` environment variables
- Bearer token header fallback for web auth (API key auth via Bearer header is unchanged)

### Fixed
- Fix pipeline clears `CLAUDECODE` env var before spawning Claude Code SDK to prevent nested-session detection failures
- Claude Code SDK stderr is now captured and logged for better diagnostics on CLI failures
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
