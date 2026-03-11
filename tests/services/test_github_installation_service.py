"""Tests for oopsie.services.github_installation_service."""

from unittest.mock import MagicMock, patch

import pytest
from oopsie.models.fix_attempt import FixAttemptStatus
from oopsie.models.github_installation import InstallationStatus
from oopsie.services.github_installation_service import (
    handle_installation_event,
    handle_pr_event,
    process_install_callback,
    upsert_installation,
)
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import (
    ErrorFactory,
    FixAttemptFactory,
    GithubInstallationFactory,
    OrganizationFactory,
    ProjectFactory,
)


def _make_installation_event(action: str, installation_id: int) -> MagicMock:
    """Return a minimal mock of a githubkit installation webhook event."""
    event = MagicMock()
    event.action = action
    event.installation.id = installation_id
    return event


def _make_pr_event(action: str, merged: bool, html_url: str) -> MagicMock:
    """Return a minimal mock of a githubkit pull_request webhook event."""
    event = MagicMock()
    event.action = action
    event.pull_request.merged = merged
    event.pull_request.html_url = html_url
    return event


# ---------------------------------------------------------------------------
# upsert_installation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_installation_creates_new(db_session: AsyncSession):
    """upsert_installation creates a new GithubInstallation when none exists."""
    org = OrganizationFactory.build()
    db_session.add(org)
    await db_session.flush()

    installation = await upsert_installation(
        session=db_session,
        organization_id=org.id,
        github_installation_id=42000,
        github_account_login="acme-corp",
    )

    assert installation.organization_id == org.id
    assert installation.github_installation_id == 42000
    assert installation.github_account_login == "acme-corp"
    assert installation.status == InstallationStatus.ACTIVE


@pytest.mark.asyncio
async def test_upsert_installation_updates_existing(db_session: AsyncSession):
    """upsert_installation updates existing record on re-install."""
    org = OrganizationFactory.build()
    db_session.add(org)
    await db_session.flush()

    existing = GithubInstallationFactory.build(
        organization_id=org.id,
        github_installation_id=10000,
        github_account_login="old-login",
        status=InstallationStatus.REMOVED,
    )
    db_session.add(existing)
    await db_session.flush()

    result = await upsert_installation(
        session=db_session,
        organization_id=org.id,
        github_installation_id=20000,
        github_account_login="new-login",
    )

    # Should update the same record, not create a new one
    assert result.id == existing.id
    assert result.github_installation_id == 20000
    assert result.github_account_login == "new-login"
    assert result.status == InstallationStatus.ACTIVE


@pytest.mark.asyncio
async def test_upsert_installation_calls_flush(db_session: AsyncSession):
    """upsert_installation calls session.flush()."""
    org = OrganizationFactory.build()
    db_session.add(org)
    await db_session.flush()

    with patch.object(db_session, "flush", wraps=db_session.flush) as mock_flush:
        await upsert_installation(
            session=db_session,
            organization_id=org.id,
            github_installation_id=42001,
            github_account_login="flush-test",
        )
        mock_flush.assert_called()


# ---------------------------------------------------------------------------
# handle_installation_event — status transitions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_installation_event_deleted(db_session: AsyncSession):
    """handle_installation_event sets REMOVED status for 'deleted' action."""
    org = OrganizationFactory.build()
    db_session.add(org)
    await db_session.flush()

    inst = GithubInstallationFactory.build(
        organization_id=org.id,
        github_installation_id=5001,
        status=InstallationStatus.ACTIVE,
    )
    db_session.add(inst)
    await db_session.flush()

    fake_event = _make_installation_event("deleted", 5001)
    raw_body = b'{"action": "deleted"}'

    with patch(
        "oopsie.services.github_installation_service.parse_webhook",
        return_value=fake_event,
    ):
        await handle_installation_event(db_session, raw_body)

    await db_session.refresh(inst)
    assert inst.status == InstallationStatus.REMOVED


@pytest.mark.asyncio
async def test_handle_installation_event_suspended(db_session: AsyncSession):
    """handle_installation_event sets SUSPENDED status for 'suspended' action."""
    org = OrganizationFactory.build()
    db_session.add(org)
    await db_session.flush()

    inst = GithubInstallationFactory.build(
        organization_id=org.id,
        github_installation_id=5002,
        status=InstallationStatus.ACTIVE,
    )
    db_session.add(inst)
    await db_session.flush()

    fake_event = _make_installation_event("suspended", 5002)
    raw_body = b'{"action": "suspended"}'

    with patch(
        "oopsie.services.github_installation_service.parse_webhook",
        return_value=fake_event,
    ):
        await handle_installation_event(db_session, raw_body)

    await db_session.refresh(inst)
    assert inst.status == InstallationStatus.SUSPENDED


@pytest.mark.asyncio
async def test_handle_installation_event_unsuspended(db_session: AsyncSession):
    """handle_installation_event sets ACTIVE status for 'unsuspended' action."""
    org = OrganizationFactory.build()
    db_session.add(org)
    await db_session.flush()

    inst = GithubInstallationFactory.build(
        organization_id=org.id,
        github_installation_id=5003,
        status=InstallationStatus.SUSPENDED,
    )
    db_session.add(inst)
    await db_session.flush()

    fake_event = _make_installation_event("unsuspended", 5003)
    raw_body = b'{"action": "unsuspended"}'

    with patch(
        "oopsie.services.github_installation_service.parse_webhook",
        return_value=fake_event,
    ):
        await handle_installation_event(db_session, raw_body)

    await db_session.refresh(inst)
    assert inst.status == InstallationStatus.ACTIVE


@pytest.mark.asyncio
async def test_handle_installation_event_unknown_action(db_session: AsyncSession):
    """handle_installation_event ignores unknown actions without raising."""
    org = OrganizationFactory.build()
    db_session.add(org)
    await db_session.flush()

    inst = GithubInstallationFactory.build(
        organization_id=org.id,
        github_installation_id=5004,
        status=InstallationStatus.ACTIVE,
    )
    db_session.add(inst)
    await db_session.flush()

    fake_event = _make_installation_event("new_permissions_accepted", 5004)
    raw_body = b'{"action": "new_permissions_accepted"}'

    with patch(
        "oopsie.services.github_installation_service.parse_webhook",
        return_value=fake_event,
    ):
        # Must not raise
        await handle_installation_event(db_session, raw_body)

    # Status should be unchanged
    await db_session.refresh(inst)
    assert inst.status == InstallationStatus.ACTIVE


@pytest.mark.asyncio
async def test_handle_installation_event_not_found(db_session: AsyncSession):
    """handle_installation_event logs warning when installation not found in DB."""
    fake_event = _make_installation_event("deleted", 99999)
    raw_body = b'{"action": "deleted"}'

    with patch(
        "oopsie.services.github_installation_service.parse_webhook",
        return_value=fake_event,
    ):
        # Must not raise even when installation is missing
        await handle_installation_event(db_session, raw_body)


# ---------------------------------------------------------------------------
# handle_pr_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_pr_event_ignores_non_closed(db_session: AsyncSession):
    """handle_pr_event ignores events where action is not 'closed'."""
    fake_event = _make_pr_event(
        "opened", merged=False, html_url="https://github.com/o/r/pull/1"
    )
    raw_body = b'{"action": "opened"}'

    with patch(
        "oopsie.services.github_installation_service.parse_webhook",
        return_value=fake_event,
    ):
        # Must not raise or mutate any state
        await handle_pr_event(db_session, raw_body)


@pytest.mark.asyncio
async def test_handle_pr_event_ignores_closed_not_merged(db_session: AsyncSession):
    """handle_pr_event ignores closed PRs where merged is False."""
    fake_event = _make_pr_event(
        "closed", merged=False, html_url="https://github.com/o/r/pull/2"
    )
    raw_body = b'{"action": "closed"}'

    with patch(
        "oopsie.services.github_installation_service.parse_webhook",
        return_value=fake_event,
    ):
        await handle_pr_event(db_session, raw_body)


@pytest.mark.asyncio
async def test_handle_pr_event_merged_updates_fix_attempt(db_session: AsyncSession):
    """handle_pr_event sets MERGED status when PR is closed+merged and url matches."""
    org = OrganizationFactory.build()
    db_session.add(org)
    await db_session.flush()

    project = ProjectFactory.build(organization_id=org.id)
    db_session.add(project)
    await db_session.flush()

    error = ErrorFactory.build(project_id=project.id)
    db_session.add(error)
    await db_session.flush()

    pr_url = "https://github.com/acme/api/pull/42"
    fix_attempt = FixAttemptFactory.build(
        error_id=error.id,
        status=FixAttemptStatus.SUCCESS,
        pr_url=pr_url,
    )
    db_session.add(fix_attempt)
    await db_session.flush()

    fake_event = _make_pr_event("closed", merged=True, html_url=pr_url)
    raw_body = b'{"action": "closed"}'

    with patch(
        "oopsie.services.github_installation_service.parse_webhook",
        return_value=fake_event,
    ):
        await handle_pr_event(db_session, raw_body)

    await db_session.refresh(fix_attempt)
    assert fix_attempt.status == FixAttemptStatus.MERGED


@pytest.mark.asyncio
async def test_handle_pr_event_merged_no_match_logs_warning(db_session: AsyncSession):
    """handle_pr_event logs warning and returns when no FixAttempt matches pr_url."""
    pr_url = "https://github.com/unknown/repo/pull/999"
    fake_event = _make_pr_event("closed", merged=True, html_url=pr_url)
    raw_body = b'{"action": "closed"}'

    with patch(
        "oopsie.services.github_installation_service.parse_webhook",
        return_value=fake_event,
    ):
        # Must not raise
        await handle_pr_event(db_session, raw_body)


# ---------------------------------------------------------------------------
# process_install_callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_install_callback_creates_installation(db_session: AsyncSession):
    """process_install_callback looks up org by slug and upserts installation."""
    org = OrganizationFactory.build()
    db_session.add(org)
    await db_session.flush()

    installation = await process_install_callback(
        db_session,
        org_slug=org.slug,
        github_installation_id=12345,
    )
    assert installation.organization_id == org.id
    assert installation.github_installation_id == 12345


@pytest.mark.asyncio
async def test_process_install_callback_org_not_found(db_session: AsyncSession):
    """process_install_callback raises ValueError for unknown org slug."""
    with pytest.raises(ValueError, match="Organization not found"):
        await process_install_callback(
            db_session,
            org_slug="nonexistent",
            github_installation_id=12345,
        )
