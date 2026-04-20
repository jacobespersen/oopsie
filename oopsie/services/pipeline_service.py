"""Orchestration logic for the fix pipeline."""

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from oopsie.config import Settings, get_settings
from oopsie.database import worker_session
from oopsie.exceptions import AnthropicKeyNotConfiguredError
from oopsie.logging import logger
from oopsie.models.error import Error, ErrorStatus
from oopsie.models.error_occurrence import ErrorOccurrence
from oopsie.models.github_installation import InstallationStatus
from oopsie.models.organization import Organization
from oopsie.models.project import Project
from oopsie.services import (
    claude_service,
    fix_service,
    github_app_service,
    github_service,
)
from oopsie.services.anthropic_key_service import resolve_anthropic_api_key


@dataclass
class _JobContext:
    """Data extracted from the DB before the clone directory is created."""

    fix_attempt_id: UUID
    branch_name: str
    error_class: str
    message: str
    stack_trace: str | None
    repo_url: str
    default_branch: str
    installation_id: int
    # Excluded from repr/str to prevent accidental key logging
    anthropic_api_key: str = field(repr=False)
    exception_chain: list[dict[str, Any]] | None = None
    execution_context: dict[str, Any] | None = None


async def _load_and_prepare(error_id: str, project_id: str) -> _JobContext | None:
    """Load error, project, org, and installation; create a PENDING fix attempt.

    Returns None if the job should be skipped (error not open, project missing,
    or no active GitHub App installation for the project's org).
    """
    async with worker_session() as session:
        error = await session.get(Error, error_id)
        if not error or error.status != ErrorStatus.OPEN:
            logger.info("fix_pipeline_skipped", error_id=error_id, reason="not_open")
            return None

        # Load project with org and installation in one query to avoid N+1
        result = await session.execute(
            select(Project)
            .where(Project.id == project_id)
            .options(
                selectinload(Project.organization).selectinload(
                    Organization.github_installation
                )
            )
        )
        project = result.scalar_one_or_none()
        if not project:
            logger.error(
                "fix_pipeline_skipped",
                error_id=error_id,
                reason="project_not_found",
            )
            return None

        installation = project.organization.github_installation
        if installation is None or installation.status != InstallationStatus.ACTIVE:
            logger.warning(
                "fix_pipeline_skipped",
                error_id=error_id,
                reason="no_github_installation",
                org_id=str(project.organization_id),
            )
            return None

        # Resolve the Anthropic API key (project → org); skip gracefully if not set
        try:
            anthropic_api_key = resolve_anthropic_api_key(
                project, get_settings().encryption_key
            )
        except AnthropicKeyNotConfiguredError:
            logger.warning(
                "fix_pipeline_skipped",
                error_id=error_id,
                reason="no_anthropic_key",
                org_id=str(project.organization_id),
            )
            return None

        # Fetch the latest occurrence for enriched context (exception chain,
        # execution context). We pick the most recent occurrence overall rather
        # than filtering for only enriched ones — this keeps the query simple
        # and the latest report is most likely to have the richest context.
        # This is optional enrichment — a failure here should not kill the
        # entire fix pipeline since the core error data is already loaded.
        latest_occurrence = None
        try:
            occurrence_result = await session.execute(
                select(ErrorOccurrence)
                .where(ErrorOccurrence.error_id == error.id)
                .order_by(ErrorOccurrence.occurred_at.desc())
                .limit(1)
            )
            latest_occurrence = occurrence_result.scalar_one_or_none()
        except Exception:
            logger.warning(
                "occurrence_context_load_failed",
                error_id=error_id,
            )

        branch_name = fix_service.generate_branch_name(error_id)
        fix_attempt = await fix_service.create_fix_attempt(
            session, error.id, branch_name
        )

        return _JobContext(
            fix_attempt_id=fix_attempt.id,
            branch_name=branch_name,
            error_class=error.error_class,
            message=error.message,
            stack_trace=error.stack_trace,
            repo_url=project.github_repo_url,
            default_branch=project.default_branch,
            installation_id=installation.github_installation_id,
            exception_chain=(
                latest_occurrence.exception_chain if latest_occurrence else None
            ),
            execution_context=(
                latest_occurrence.execution_context if latest_occurrence else None
            ),
            anthropic_api_key=anthropic_api_key,
        )


def _build_pr_body(ctx: _JobContext) -> str:
    """Build the pull request body, including enriched context if available."""
    parts = [f"Auto-fix by Oopsie for error `{ctx.error_class}`: {ctx.message}"]

    if ctx.exception_chain:
        chain_summary = ", ".join(e.get("type", "?") for e in ctx.exception_chain)
        parts.append(f"\n**Exception chain:** {chain_summary}")

    if ctx.execution_context:
        desc = ctx.execution_context.get(
            "description", ctx.execution_context.get("type", "")
        )
        parts.append(f"\n**Context:** {desc}")

    if ctx.stack_trace:
        parts.append(f"\n```\n{ctx.stack_trace}\n```")
    elif not ctx.exception_chain:
        parts.append("\nNo stack trace")

    return "\n".join(parts)


async def _run_fix(clone_dir: str, ctx: _JobContext, settings: Settings) -> str:
    """Clone repo, create branch, run Claude, commit and push.

    Returns the PR URL on success. Raises on any failure.
    """
    # Exchange the app JWT for a short-lived installation access token.
    # Raises GitHubApiError if the API call fails — caught by the caller.
    token = await github_app_service.get_installation_token(ctx.installation_id)

    owner, repo_name = github_service.parse_repo_owner_name(ctx.repo_url)

    await github_service.clone_repo(ctx.repo_url, token, ctx.default_branch, clone_dir)
    await github_service.create_branch(clone_dir, ctx.branch_name)

    claude_output = await claude_service.run_claude_code(
        clone_dir,
        ctx.error_class,
        ctx.message,
        ctx.stack_trace,
        ctx.anthropic_api_key,
        settings.job_timeout_seconds,
        exception_chain=ctx.exception_chain,
        execution_context=ctx.execution_context,
    )

    if not await github_service.has_changes(clone_dir):
        logger.warning(
            "claude_no_changes",
            claude_output=claude_output,
            error_id=str(ctx.fix_attempt_id),
        )
        raise ValueError(
            f"Claude produced no changes.\n\nClaude's response:\n{claude_output}"
        )

    commit_msg = f"fix: resolve {ctx.error_class} — {ctx.message[:60]}"
    await github_service.commit_and_push(
        clone_dir, ctx.branch_name, commit_msg, token, ctx.repo_url
    )

    return await github_service.create_pull_request(
        owner,
        repo_name,
        token,
        ctx.branch_name,
        ctx.default_branch,
        title=f"[Oopsie] {commit_msg}",
        body=_build_pr_body(ctx),
    )


async def run(error_id: str, project_id: str) -> None:
    """Load context, run the fix, record the outcome."""
    settings = get_settings()
    logger.info("fix_pipeline_started", error_id=error_id, project_id=project_id)

    job_ctx = await _load_and_prepare(error_id, project_id)
    if job_ctx is None:
        return

    os.makedirs(settings.clone_base_path, exist_ok=True)
    clone_dir = tempfile.mkdtemp(
        dir=settings.clone_base_path, prefix=f"fix-{error_id[:8]}-"
    )
    try:
        async with worker_session() as session:
            await fix_service.mark_fix_attempt_running(session, job_ctx.fix_attempt_id)

        pr_url = await _run_fix(clone_dir, job_ctx, settings)

        async with worker_session() as session:
            await fix_service.complete_fix_attempt(
                session,
                job_ctx.fix_attempt_id,
                success=True,
                pr_url=pr_url,
                claude_output=None,
            )
        logger.info("fix_pipeline_success", error_id=error_id, pr_url=pr_url)

    except Exception as exc:
        logger.error("fix_pipeline_failed", error_id=error_id, error=str(exc))
        async with worker_session() as session:
            await fix_service.complete_fix_attempt(
                session,
                job_ctx.fix_attempt_id,
                success=False,
                pr_url=None,
                claude_output=str(exc),
            )
    finally:
        shutil.rmtree(clone_dir, ignore_errors=True)
