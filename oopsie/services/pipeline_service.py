"""Orchestration logic for the fix pipeline."""

import os
import shutil
import tempfile
from dataclasses import dataclass
from uuid import UUID

from oopsie.config import Settings, get_settings
from oopsie.database import worker_session
from oopsie.logging import logger
from oopsie.models.error import Error, ErrorStatus
from oopsie.models.project import Project
from oopsie.services import claude_service, fix_service, github_service


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


async def _load_and_prepare(error_id: str, project_id: str) -> _JobContext | None:
    """Load error + project, validate state, and create a PENDING fix attempt.

    Returns None if the job should be skipped (error not open, project missing).
    """
    async with worker_session() as session:
        error = await session.get(Error, error_id)
        if not error or error.status != ErrorStatus.OPEN:
            logger.info("fix_pipeline_skipped", error_id=error_id, reason="not_open")
            return None

        project = await session.get(Project, project_id)
        if not project:
            logger.error(
                "fix_pipeline_skipped",
                error_id=error_id,
                reason="project_not_found",
            )
            return None

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
        )


# TODO Phase 4: replace empty token strings with installation access token
# from github_app_service
async def _run_fix(clone_dir: str, ctx: _JobContext, settings: Settings) -> str:
    """Clone repo, create branch, run Claude, commit and push.

    Returns the PR URL on success. Raises on any failure.
    """
    owner, repo_name = github_service.parse_repo_owner_name(ctx.repo_url)

    await github_service.clone_repo(ctx.repo_url, "", ctx.default_branch, clone_dir)
    await github_service.create_branch(clone_dir, ctx.branch_name)

    await claude_service.run_claude_code(
        clone_dir,
        ctx.error_class,
        ctx.message,
        ctx.stack_trace,
        settings.anthropic_api_key,
        settings.job_timeout_seconds,
    )

    if not await github_service.has_changes(clone_dir):
        raise ValueError("Claude produced no changes")

    commit_msg = f"fix: resolve {ctx.error_class} — {ctx.message[:60]}"
    await github_service.commit_and_push(
        clone_dir, ctx.branch_name, commit_msg, "", ctx.repo_url
    )

    return await github_service.create_pull_request(
        owner,
        repo_name,
        "",
        ctx.branch_name,
        ctx.default_branch,
        title=f"[Oopsie] {commit_msg}",
        body=(
            f"Auto-fix by Oopsie for error `{ctx.error_class}`: {ctx.message}\n\n"
            f"```\n{ctx.stack_trace or 'No stack trace'}\n```"
        ),
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
