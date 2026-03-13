# Codebase Concerns

**Analysis Date:** 2026-03-13

## Tech Debt

**Assert statements in production code:**
- Issue: `session.get()` calls in `fix_service.py` (lines 54, 72, 83) use `assert` to verify DB objects exist, but assertions are removed in Python optimized mode (`python -O`). In production environments with optimization enabled, these become no-ops.
- Files: `oopsie/services/fix_service.py` (lines 54, 72, 83)
- Impact: If a `FixAttempt` or `Error` record is deleted between fetches or doesn't exist, the code will crash with an `AttributeError` instead of a controlled error, causing unhandled exceptions in the worker pipeline.
- Fix approach: Replace assertions with explicit `if not` checks that raise descriptive errors. Example: `if not fix_attempt: raise ValueError("FixAttempt not found")`

**Revoked token table cleanup not implemented:**
- Issue: The `RevokedToken` table accumulates expired rows indefinitely. No cleanup mechanism exists.
- Files: `oopsie/models/revoked_token.py` (lines 2-5), referenced in `oopsie/auth.py`
- Impact: Over months/years, the revoked tokens table will grow unbounded, increasing query latency and storage costs. Token revocation checks (`decode_jwt_token` in `auth.py` line 98-102) will scan an ever-larger table.
- Fix approach: Add a periodic background job (via arq) that runs `DELETE FROM revoked_tokens WHERE expires_at < now()` nightly. Schedule via worker settings or a separate cron-like task.

**No database connection pool configuration:**
- Issue: `oopsie/database.py` uses `create_async_engine()` with default connection pool settings (pool_size=5, max_overflow=10). No explicit tuning for concurrency or resource limits.
- Files: `oopsie/database.py` (lines 29-33)
- Impact: Under high load or with many concurrent workers, connection exhaustion can cause `sqlalchemy.exc.TimeoutError` or connection pool deadlocks. The worker (default 3 concurrency, line 30 in `config.py`) and web app share no connection pool coordination.
- Fix approach: Tune `pool_size` and `max_overflow` based on expected concurrency. Add monitoring for pool exhaustion. Consider connection pooling via PgBouncer for production.

**Temporary clone directories may not be cleaned up on worker crash:**
- Issue: `oopsie/services/pipeline_service.py` (lines 153-184) creates temp directories in `clone_base_path` but only removes them in a `finally` block. If the worker process crashes hard (SIGKILL) or runs out of disk, cleanup is skipped.
- Files: `oopsie/services/pipeline_service.py` (lines 153-184), `oopsie/config.py` (line 32)
- Impact: Stale clone directories accumulate in `/tmp/oopsie-clones`, consuming disk space and potentially filling the volume over weeks of operation.
- Fix approach: Implement a scheduled cleanup job that removes clone directories older than N hours. Add monitoring for disk usage on the worker container.

## Security Considerations

**GitHub API tokens leaked in error logs:**
- Issue: `oopsie/services/github_service.py` (line 50) injects tokens into git clone URLs. If git operations fail, stderr is captured and logged in `oopsie/services/pipeline_service.py` (line 174) as `str(exc)`. Token-containing error messages are written to `claude_output` field in the database.
- Files: `oopsie/services/github_service.py` (lines 42-50), `oopsie/services/pipeline_service.py` (line 174)
- Current mitigation: Error messages are stored in the DB but not exposed to the web UI. They are only visible via internal logs/monitoring.
- Recommendations: Add a sanitization function that strips tokens from error messages before logging or storing. Mask tokens in log output. Use `x-access-token:token@host` safely but consider passing token separately as a git credential helper instead of embedding in URLs.

**No API key rotation mechanism:**
- Issue: Project API keys in `oopsie/models/project.py` are stored as one-way SHA-256 hashes but there is no key rotation or revocation UI. A compromised key can be used indefinitely until manually deleted.
- Files: `oopsie/models/project.py`, `oopsie/deps.py` (line 37)
- Current mitigation: Keys are per-project and can be deleted by org admins.
- Recommendations: Add a UI to regenerate API keys (invalidate old hash, create new one). Log all API key regenerations. Consider implementing short-lived bearer tokens with expiration.

**Cookie security not enforced in dev:**
- Issue: `oopsie/main.py` (line 52) uses `SessionMiddleware` with `secret_key` set to `jwt_secret_key`. If `cookie_secure=False` (default in `config.py` line 41), cookies are not marked Secure and will be sent over HTTP.
- Files: `oopsie/main.py` (lines 52-53), `oopsie/config.py` (line 41)
- Current mitigation: This is intentional for local development, but production deployments must ensure `cookie_secure=True` and HTTPS enforcement.
- Recommendations: Explicitly set `SessionMiddleware(..., cookie_secure=settings.cookie_secure, cookie_httponly=True, cookie_samesite="lax")` in main.py. Document that production deployments require `cookie_secure=True`.

**No rate limiting on error ingestion API:**
- Issue: `oopsie/api/errors.py` accepts error reports without rate limiting. A malicious client can spam the API to DOS the system or fill the database.
- Files: `oopsie/api/errors.py` (lines 22-40)
- Impact: No limits on errors per project per time window; attackers can create thousands of errors and FixAttempts, consuming API quota and triggering expensive Claude Code runs.
- Recommendations: Implement per-project rate limiting (e.g., 1000 errors/hour per API key). Use Redis for distributed rate limiting via arq.

**GitHub webhook signature verification not enforced globally:**
- Issue: `oopsie/web/github.py` calls `verify_webhook()` but the signature verification is only performed in webhook handlers, not enforced at the middleware level. If handlers are added without verification, they are vulnerable.
- Files: `oopsie/web/github.py`, `oopsie/services/github_app_service.py` (line 94)
- Recommendations: Move webhook signature verification to a dependency (`Depends()`) that all GitHub webhook routes use, or implement at the middleware level to protect all `/webhook/*` routes.

## Performance Bottlenecks

**Potential N+1 query in fix status batch endpoint:**
- Issue: `oopsie/services/fix_service.py` (lines 107-129, `get_fix_attempt_status_for_errors`) fetches all FixAttempts for multiple errors without selective loading. If called with 100 error IDs, it retrieves all attempts (potentially thousands of rows) and filters in Python.
- Files: `oopsie/services/fix_service.py` (lines 107-129)
- Impact: Large result sets cause memory overhead and slow queries for high-volume projects.
- Improvement path: Add a `LIMIT 1` or `DISTINCT ON (error_id)` in the SQL query to fetch only the latest attempt per error. Use window functions: `SELECT DISTINCT ON (error_id) * FROM fix_attempts ORDER BY error_id, created_at DESC`.

**Claude Code subprocess no timeout protection at container level:**
- Issue: `oopsie/services/claude_service.py` (line 55) uses `asyncio.wait_for()` with a timeout, but if Claude Code spawns child processes that don't inherit the timeout, those children may persist after the timeout fires.
- Files: `oopsie/services/claude_service.py` (lines 26-68)
- Impact: Runaway child processes consume worker resources indefinitely; the worker may become unresponsive.
- Improvement path: Use `asyncio.create_subprocess_exec(..., preexec_fn=os.setpgrp)` to create a process group, then kill the entire group on timeout. Or use resource limits via `resource.setrlimit()` (CPU time, memory).

**Clone operations use shallow clone but no size limits:**
- Issue: `oopsie/services/github_service.py` (lines 48-61, `clone_repo`) uses `--depth 1` for shallow clones, which is good, but does not limit download size. A repository with large binary files or Git LFS pointers can still consume significant bandwidth and disk space.
- Files: `oopsie/services/github_service.py` (lines 48-61)
- Impact: Large repos (> 1 GB) can fill worker disk, especially if multiple concurrent jobs clone the same large repo.
- Improvement path: Add `--single-branch` flag to reduce refs downloaded. Implement a max-size check post-clone: if `du -sh clone_dir` exceeds a threshold, abort the job. Use `GIT_CONFIG_GLOBAL` to set `core.longpaths=false` on Windows-like systems.

## Fragile Areas

**Fix pipeline orchestration assumes successful intermediate steps:**
- Issue: `oopsie/services/pipeline_service.py` (lines 99-141, `_run_fix`) chains multiple async operations (clone, branch, Claude, commit, push) without intermediate checkpoints. If the push fails, no PR is created, but the branch and commits remain on the remote.
- Files: `oopsie/services/pipeline_service.py` (lines 99-141)
- Why fragile: PR URL is not recorded if push fails; branch cleanup is not automatic. Logs show the error but the state is partially committed.
- Safe modification: Add idempotency keys and persist intermediate state (e.g., "commits_pushed", "pr_created") in `FixAttempt` model. On retry, skip already-completed steps.
- Test coverage: No tests for push failures with orphaned branches; error recovery path is untested.

**Database session lifecycle in worker vs. web app differs:**
- Issue: `oopsie/database.py` provides `worker_session()` for the worker and `get_session()` for FastAPI. `worker_session()` calls `session.commit()` (line 49), while `get_session()` only yields the session (line 61). The web app commits at a higher scope (middleware or endpoint).
- Files: `oopsie/database.py` (lines 43-61)
- Why fragile: If a service function is shared between worker and web handlers, the semantics differ: worker commits immediately, web app expects the caller to commit. This can lead to uncommitted changes in the web app or premature commits in the worker.
- Safe modification: Adopt a uniform "services don't commit" policy. Services call `session.flush()` to check constraints; the caller (worker or web endpoint) commits. Update `worker_session()` to only flush.
- Test coverage: No tests that verify both worker and web app persistence patterns work identically.

**GitHub installation status not checked at middleware level:**
- Issue: Endpoints that use GitHub features check `installation.status == ACTIVE` at the service level, but there is no centralized guard. Stale installations with `SUSPENDED` status are still usable until an endpoint is called.
- Files: `oopsie/services/pipeline_service.py` (lines 72-80), `oopsie/web/github.py`
- Why fragile: Business logic is scattered across endpoints and services; a new endpoint that uses GitHub features might forget the check.
- Safe modification: Create a `RequireGitHubInstallation` dependency that verifies the org has an active installation before allowing the handler to run.

## Test Coverage Gaps

**No tests for fix pipeline with push failures:**
- What's not tested: `_run_fix()` in `pipeline_service.py` has no mocked failure scenarios for git push. If the remote branch already exists or push is rejected, the behavior is untested.
- Files: `oopsie/services/pipeline_service.py` (lines 99-141), `tests/worker/test_fix_pipeline.py`
- Risk: Regression in push handling goes undetected until production.
- Priority: High - push failures are common in real systems.

**No tests for revoked token cleanup expiry:**
- What's not tested: Tokens with expired `expires_at` values are not tested for deletion or cleanup behavior.
- Files: `oopsie/models/revoked_token.py`, `oopsie/auth.py` (lines 98-102)
- Risk: Cleanup jobs, when implemented, may have off-by-one errors or time zone bugs.
- Priority: Medium - cleanup is not yet implemented.

**No tests for database connection pool exhaustion:**
- What's not tested: Concurrent requests that exceed pool capacity are not simulated.
- Files: `oopsie/database.py`
- Risk: Pool exhaustion bugs only surface under production load.
- Priority: Medium - requires load testing infrastructure.

**No integration tests for GitHub webhook handling:**
- What's not tested: Webhook signature verification, payload parsing, and event routing are not tested end-to-end.
- Files: `oopsie/web/github.py`, `oopsie/services/github_app_service.py` (line 94)
- Risk: Malformed or replayed webhooks may bypass verification.
- Priority: High - webhook attacks are a real security risk.

## Scaling Limits

**Worker concurrency hardcoded to 3:**
- Current capacity: 3 concurrent fix jobs per worker instance.
- Limit: With `job_timeout_seconds=600` (10 minutes), a worker can process ~18 jobs/hour. High-volume projects may queue indefinitely.
- Scaling path: Make `worker_concurrency` configurable via env var. Horizontal scaling: run multiple worker instances behind the same Redis queue. Monitor queue depth via Prometheus metrics.

**Redis as single point of failure:**
- Current capacity: `REDIS_URL` is required; no fallback or replication.
- Limit: Redis unavailability halts all job processing.
- Scaling path: Configure Redis Sentinel or Cluster for high availability. Implement health checks and circuit breakers.

**Clone base path uses local filesystem:**
- Current capacity: `/tmp/oopsie-clones` is a local volume. Multi-worker deployments cannot share clone state.
- Limit: Each worker must have its own clone storage; no deduplication across workers.
- Scaling path: Consider a shared NFS mount for clone caches (with cache-busting per repo hash). Or use S3/Blob storage for artifact storage.

## Scaling Limits (continued)

**Database connection pool not tuned for concurrency:**
- Current capacity: Default SQLAlchemy pool is 5 connections with 10 overflow. With 3 worker jobs + multiple web requests, contention is likely.
- Limit: Connection starvation under load.
- Scaling path: Increase `pool_size` to 20-30 for production, or use PgBouncer for connection multiplexing.

## Known Issues

**Partial GitHub App configuration warning is non-blocking:**
- Issue: If only 1-2 of `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY_PEM`, `GITHUB_WEBHOOK_SECRET` are set, a warning is issued but the app starts anyway (line 115-120 in `config.py`).
- Impact: GitHub features silently fail at runtime instead of failing fast at startup.
- Workaround: Set all three or none.
- Fix approach: Change validation from `warning` to `raise ValueError` if partial config is detected.

**Error fingerprinting determinism not documented:**
- Issue: `oopsie/utils/fingerprint.py` contains the fingerprinting logic, but the contract (what fields matter, what hash algorithm) is not documented. If the algorithm changes, old fingerprints become incomparable with new ones.
- Impact: Changing fingerprinting logic splits error deduplication.
- Recommendations: Document the fingerprint algorithm and version it. Add a migration path if the algorithm needs to change.

---

*Concerns audit: 2026-03-13*
