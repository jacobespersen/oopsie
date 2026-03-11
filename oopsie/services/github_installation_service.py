"""Business logic for GitHub installation lifecycle and webhook events.

Called from web/github.py. Keeps routing thin by isolating all
DB interaction and dispatch logic here.
"""

import uuid

from githubkit.webhooks import parse as parse_webhook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.logging import logger
from oopsie.models.fix_attempt import FixAttempt, FixAttemptStatus
from oopsie.models.github_installation import GithubInstallation, InstallationStatus
from oopsie.services import github_app_service
from oopsie.services.exceptions import GitHubApiError

# Maps GitHub webhook action strings to InstallationStatus values.
# Only these three actions modify DB state; others are logged and ignored.
_INSTALLATION_ACTION_MAP: dict[str, InstallationStatus] = {
    "deleted": InstallationStatus.REMOVED,
    "suspended": InstallationStatus.SUSPENDED,
    "unsuspended": InstallationStatus.ACTIVE,
}


async def process_install_callback(
    session: AsyncSession,
    org_slug: str,
    github_installation_id: int,
) -> GithubInstallation:
    """Look up org by slug and upsert the GitHub installation.

    Raises ValueError if the org slug does not match any organization.
    """
    from oopsie.models.organization import Organization

    result = await session.execute(
        select(Organization).where(Organization.slug == org_slug)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise ValueError(f"Organization not found: {org_slug}")

    return await upsert_installation(
        session,
        organization_id=org.id,
        github_installation_id=github_installation_id,
        github_account_login="",  # Populated in Phase 4 via GitHub API
    )


async def get_installation_repos(
    session: AsyncSession,
    organization_id: uuid.UUID,
) -> tuple[GithubInstallation | None, list[str], str | None]:
    """Fetch the active installation and its accessible repos for an org.

    Returns (installation, repos, error_message). If the GitHub API call
    fails, repos is empty and error_message describes the failure.
    """
    result = await session.execute(
        select(GithubInstallation).where(
            GithubInstallation.organization_id == organization_id
        )
    )
    installation = result.scalar_one_or_none()

    if not installation or installation.status != InstallationStatus.ACTIVE:
        return installation, [], None

    try:
        repos = await github_app_service.list_installation_repos(
            installation.github_installation_id
        )
        return installation, repos, None
    except GitHubApiError as exc:
        logger.warning(
            "list_repos_failed",
            organization_id=str(organization_id),
            error=str(exc),
        )
        return installation, [], str(exc)


async def upsert_installation(
    session: AsyncSession,
    organization_id: uuid.UUID,
    github_installation_id: int,
    github_account_login: str | None,
) -> GithubInstallation:
    """Create or update the GithubInstallation record for an org.

    When the org already has an installation record (e.g. a re-install),
    the existing row is updated in-place with the new GitHub installation ID,
    account login, and ACTIVE status. A new row is created on first install.
    Flushes before returning so callers can rely on the persisted state.

    Args:
        session: The current async DB session.
        organization_id: Oopsie's UUID for the organization.
        github_installation_id: GitHub's numeric installation ID.
        github_account_login: The GitHub account slug (org or user login).

    Returns:
        The created or updated GithubInstallation.
    """
    result = await session.execute(
        select(GithubInstallation).where(
            GithubInstallation.organization_id == organization_id
        )
    )
    installation = result.scalar_one_or_none()

    if installation:
        # Re-install scenario: update the existing record rather than creating
        # a duplicate. The UniqueConstraint on organization_id enforces one row.
        installation.github_installation_id = github_installation_id
        installation.github_account_login = github_account_login
        installation.status = InstallationStatus.ACTIVE
        logger.info(
            "installation_updated",
            organization_id=str(organization_id),
            github_installation_id=github_installation_id,
        )
    else:
        installation = GithubInstallation(
            organization_id=organization_id,
            github_installation_id=github_installation_id,
            github_account_login=github_account_login,
            status=InstallationStatus.ACTIVE,
        )
        session.add(installation)
        logger.info(
            "installation_created",
            organization_id=str(organization_id),
            github_installation_id=github_installation_id,
        )

    await session.flush()
    return installation


async def handle_installation_event(
    session: AsyncSession,
    raw_body: bytes,
) -> None:
    """Handle a GitHub 'installation' webhook event.

    Parses the payload and dispatches on action. Known actions (deleted,
    suspended, unsuspended) update the corresponding GithubInstallation row.
    Unknown actions are logged and silently ignored — GitHub may send events
    we don't care about (e.g. 'new_permissions_accepted').

    The lookup key is GitHub's numeric installation ID, never Oopsie's UUID.

    Args:
        session: The current async DB session.
        raw_body: Raw webhook request body bytes.
    """
    event = parse_webhook("installation", raw_body)
    action: str = event.action
    installation_id: int = event.installation.id

    new_status = _INSTALLATION_ACTION_MAP.get(action)
    if new_status is None:
        logger.info("installation_event_ignored", action=action)
        return

    result = await session.execute(
        select(GithubInstallation).where(
            GithubInstallation.github_installation_id == installation_id
        )
    )
    installation = result.scalar_one_or_none()

    if installation is None:
        logger.warning(
            "github_installation_not_found",
            github_installation_id=installation_id,
        )
        return

    installation.status = new_status
    await session.flush()
    logger.info(
        "installation_status_updated",
        github_installation_id=installation_id,
        status=new_status,
    )


async def handle_pr_event(
    session: AsyncSession,
    raw_body: bytes,
) -> None:
    """Handle a GitHub 'pull_request' webhook event.

    Only acts on closed+merged PRs. Looks up the matching FixAttempt by
    pr_url and transitions its status to MERGED. If no FixAttempt matches
    the PR URL, logs a warning and returns — this is normal when a merged PR
    wasn't opened by Oopsie.

    Args:
        session: The current async DB session.
        raw_body: Raw webhook request body bytes.
    """
    event = parse_webhook("pull_request", raw_body)

    # Guard: only process closed, merged PRs
    if event.action != "closed" or not event.pull_request.merged:
        return

    pr_url: str = event.pull_request.html_url

    result = await session.execute(
        select(FixAttempt).where(FixAttempt.pr_url == pr_url)
    )
    fix_attempt = result.scalar_one_or_none()

    if fix_attempt is None:
        logger.warning("pr_merged_no_fix_attempt", pr_url=pr_url)
        return

    fix_attempt.status = FixAttemptStatus.MERGED
    await session.flush()
    logger.info(
        "fix_attempt_merged",
        fix_attempt_id=str(fix_attempt.id),
        pr_url=pr_url,
    )
