"""Tests for GitHub install flow and webhook routes."""

from unittest.mock import AsyncMock, patch

import pytest
from githubkit.webhooks import sign as webhook_sign
from oopsie.models.github_installation import GithubInstallation, InstallationStatus
from oopsie.models.membership import MemberRole
from sqlalchemy import select

from tests.conftest import set_membership_role


@pytest.mark.asyncio
async def test_install_redirect_303(authenticated_client, organization):
    """GET /orgs/{slug}/github/install by admin returns 303.

    Location header must contain github.com/apps/.
    """
    # current_user is already admin in organization (via fixture)
    resp = await authenticated_client.get(
        f"/orgs/{organization.slug}/github/install", follow_redirects=False
    )
    assert resp.status_code == 303
    assert "github.com/apps/" in resp.headers["location"]


@pytest.mark.asyncio
async def test_install_redirect_sets_session_state(authenticated_client, organization):
    """Session contains github_install_state after install redirect."""
    # current_user is already admin in organization (via fixture)
    resp = await authenticated_client.get(
        f"/orgs/{organization.slug}/github/install", follow_redirects=False
    )
    assert resp.status_code == 303
    # State should be embedded in the redirect URL
    location = resp.headers["location"]
    assert "state=" in location


@pytest.mark.asyncio
async def test_install_redirect_403_non_admin(
    authenticated_client, current_user, organization, db_session
):
    """GET /orgs/{slug}/github/install by a member (not admin) -> 403."""
    await set_membership_role(
        db_session, current_user.id, organization.id, MemberRole.member
    )

    resp = await authenticated_client.get(
        f"/orgs/{organization.slug}/github/install", follow_redirects=False
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_install_callback_creates_installation(
    authenticated_client, organization, db_session
):
    """GET /github/callback with valid state -> 303, GithubInstallation created."""
    # current_user is already admin in organization (via fixture)

    # Hit install redirect to store state in session
    redirect_resp = await authenticated_client.get(
        f"/orgs/{organization.slug}/github/install", follow_redirects=False
    )
    assert redirect_resp.status_code == 303

    # Extract state from the redirect URL
    location = redirect_resp.headers["location"]
    state_param = [
        p for p in location.split("?", 1)[1].split("&") if p.startswith("state=")
    ][0]
    state_value = state_param.split("=", 1)[1]

    # Call the callback with the extracted state
    cb_resp = await authenticated_client.get(
        "/github/callback",
        params={
            "installation_id": "42",
            "setup_action": "install",
            "state": state_value,
        },
        follow_redirects=False,
    )
    assert cb_resp.status_code == 303
    assert f"/orgs/{organization.slug}/settings" in cb_resp.headers["location"]

    # Verify GithubInstallation was created
    result = await db_session.execute(
        select(GithubInstallation).where(
            GithubInstallation.organization_id == organization.id
        )
    )
    installation = result.scalar_one_or_none()
    assert installation is not None
    assert installation.github_installation_id == 42


@pytest.mark.asyncio
async def test_callback_requires_authentication(api_client):
    """Unauthenticated request to callback should return 401."""
    resp = await api_client.get(
        "/github/callback",
        params={"installation_id": 123, "setup_action": "install", "state": "abc"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_install_callback_state_mismatch(authenticated_client, organization):
    """GET /github/callback with wrong state -> 400."""
    # current_user is already admin in organization (via fixture)

    # Hit install redirect to set session state
    await authenticated_client.get(
        f"/orgs/{organization.slug}/github/install", follow_redirects=False
    )

    # Call callback with wrong state
    cb_resp = await authenticated_client.get(
        "/github/callback",
        params={
            "installation_id": "42",
            "setup_action": "install",
            "state": "wrong-state-value",
        },
        follow_redirects=False,
    )
    assert cb_resp.status_code == 400


@pytest.mark.asyncio
async def test_webhook_valid_signature_installation(
    authenticated_client, current_user, factory
):
    """POST /webhooks/github with valid sig and installation event -> 200."""
    secret = "test-webhook-secret"
    body = b'{"action": "created", "installation": {"id": 1}}'
    sig = webhook_sign(secret, body)

    with (
        patch("oopsie.web.github.get_settings") as mock_settings,
        patch(
            "oopsie.web.github.handle_installation_event", new_callable=AsyncMock
        ) as mock_handler,
    ):
        mock_settings.return_value.github_webhook_secret = secret
        mock_handler.return_value = None

        resp = await authenticated_client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "installation",
                "Content-Type": "application/json",
            },
        )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    mock_handler.assert_called_once()


@pytest.mark.asyncio
async def test_webhook_valid_signature_pull_request(
    authenticated_client, current_user, factory
):
    """POST /webhooks/github with valid sig and pull_request event -> 200."""
    secret = "test-webhook-secret"
    body = b'{"action": "closed", "pull_request": {"merged": true}}'
    sig = webhook_sign(secret, body)

    with (
        patch("oopsie.web.github.get_settings") as mock_settings,
        patch(
            "oopsie.web.github.handle_pr_event", new_callable=AsyncMock
        ) as mock_handler,
    ):
        mock_settings.return_value.github_webhook_secret = secret
        mock_handler.return_value = None

        resp = await authenticated_client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "pull_request",
                "Content-Type": "application/json",
            },
        )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    mock_handler.assert_called_once()


@pytest.mark.asyncio
async def test_webhook_invalid_signature(authenticated_client):
    """POST /webhooks/github with bad sig -> 403."""
    body = b'{"action": "created"}'

    with patch("oopsie.web.github.get_settings") as mock_settings:
        mock_settings.return_value.github_webhook_secret = "real-secret"

        resp = await authenticated_client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": "sha256=badhash",
                "X-GitHub-Event": "installation",
                "Content-Type": "application/json",
            },
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_webhook_missing_signature(authenticated_client):
    """POST /webhooks/github with no X-Hub-Signature-256 -> 403."""
    body = b'{"action": "created"}'

    with patch("oopsie.web.github.get_settings") as mock_settings:
        mock_settings.return_value.github_webhook_secret = "real-secret"

        resp = await authenticated_client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Event": "installation",
                "Content-Type": "application/json",
            },
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_webhook_unknown_event_returns_200(authenticated_client):
    """POST /webhooks/github with valid sig and unknown event -> 200."""
    secret = "test-webhook-secret"
    body = b'{"ref": "refs/heads/main"}'
    sig = webhook_sign(secret, body)

    with patch("oopsie.web.github.get_settings") as mock_settings:
        mock_settings.return_value.github_webhook_secret = secret

        resp = await authenticated_client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "push",
                "Content-Type": "application/json",
            },
        )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_webhook_rejects_when_secret_not_configured(authenticated_client):
    """Webhook returns 500 when GITHUB_WEBHOOK_SECRET is empty."""
    with patch("oopsie.web.github.get_settings") as mock_settings:
        mock_settings.return_value.github_webhook_secret = ""

        resp = await authenticated_client.post(
            "/webhooks/github",
            content=b'{"action": "test"}',
            headers={
                "X-Hub-Signature-256": "sha256=abc",
                "X-GitHub-Event": "ping",
            },
        )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_webhook_returns_200_on_parse_error(authenticated_client):
    """Malformed payload with valid signature returns 200, not 500."""
    secret = "test-webhook-secret"
    body = b"not valid json at all"
    sig = webhook_sign(secret, body)

    with patch("oopsie.web.github.get_settings") as mock_settings:
        mock_settings.return_value.github_webhook_secret = secret

        resp = await authenticated_client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "installation",
                "Content-Type": "application/json",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


@pytest.mark.asyncio
async def test_settings_page_200_no_installation(
    authenticated_client, current_user, organization, db_session
):
    """GET /orgs/{slug}/settings by member -> 200, 'Not connected' in response."""
    await set_membership_role(
        db_session, current_user.id, organization.id, MemberRole.member
    )

    resp = await authenticated_client.get(f"/orgs/{organization.slug}/settings")
    assert resp.status_code == 200
    assert "Not connected" in resp.text


@pytest.mark.asyncio
async def test_settings_page_shows_active_installation(
    authenticated_client, current_user, organization, db_session, factory
):
    """GET /orgs/{slug}/settings with ACTIVE GithubInstallation returns 200.

    Response text must contain 'Connected'.
    """
    from tests.factories import GithubInstallationFactory

    await set_membership_role(
        db_session, current_user.id, organization.id, MemberRole.member
    )
    await factory(
        GithubInstallationFactory,
        organization_id=organization.id,
        status=InstallationStatus.ACTIVE,
        github_account_login="my-gh-org",
    )

    resp = await authenticated_client.get(f"/orgs/{organization.slug}/settings")
    assert resp.status_code == 200
    assert "Connected" in resp.text


@pytest.mark.asyncio
async def test_settings_page_shows_members(
    authenticated_client, current_user, organization, db_session
):
    """GET /orgs/{slug}/settings -> 200, member email in response text."""
    await set_membership_role(
        db_session, current_user.id, organization.id, MemberRole.member
    )

    resp = await authenticated_client.get(f"/orgs/{organization.slug}/settings")
    assert resp.status_code == 200
    assert current_user.email in resp.text


@pytest.mark.asyncio
async def test_settings_page_403_non_member(authenticated_client, factory):
    """GET /orgs/{slug}/settings by non-member -> 403."""
    from tests.factories import OrganizationFactory

    await factory(OrganizationFactory, slug="settings-nonmember-co")

    resp = await authenticated_client.get("/orgs/settings-nonmember-co/settings")
    assert resp.status_code == 403
