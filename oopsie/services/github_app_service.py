"""GitHub App authentication primitives.

Provides lazy-singleton app client, installation-scoped clients, and raw
installation access tokens. All GitHub App operations (webhook verification,
repo listing, pipeline token injection) depend on these three functions.
"""

from githubkit import AppAuthStrategy, GitHub

from oopsie.config import get_settings
from oopsie.logging import logger
from oopsie.services.exceptions import GitHubApiError, GitHubAppNotConfiguredError

# Module-level singleton for the GitHub App client.
# Lazy-initialized on first call to get_app_client().
_app_client: GitHub | None = None


def get_app_client() -> GitHub:
    """Return a singleton GitHub client authenticated as the GitHub App.

    Raises GitHubAppNotConfiguredError if GITHUB_APP_ID or
    GITHUB_APP_PRIVATE_KEY_PEM is not configured.
    """
    global _app_client
    if _app_client is None:
        settings = get_settings()
        if not settings.github_app_id:
            raise GitHubAppNotConfiguredError(
                "GITHUB_APP_ID is not configured. "
                "Set the GITHUB_APP_ID environment variable."
            )
        private_key_bytes = settings.github_app_private_key_bytes
        if not private_key_bytes:
            raise GitHubAppNotConfiguredError(
                "GITHUB_APP_PRIVATE_KEY_PEM is not configured. "
                "Set the GITHUB_APP_PRIVATE_KEY_PEM environment variable."
            )
        _app_client = GitHub(
            AppAuthStrategy(
                app_id=settings.github_app_id,
                # AppAuthStrategy expects the PEM as a string
                private_key=private_key_bytes.decode("utf-8"),
            )
        )
        logger.info(
            "github_app_client_initialized",
            app_id=settings.github_app_id,
        )
    return _app_client


def get_installation_client(installation_id: int) -> GitHub:
    """Return a GitHub client scoped to the given installation.

    A new client is returned on every call — installation IDs vary per
    request so caching here would be incorrect.
    """
    app = get_app_client()
    return app.with_auth(app.auth.as_installation(installation_id))


async def get_installation_token(installation_id: int) -> str:
    """Return a raw installation access token string.

    Calls the GitHub REST API to exchange the app JWT for a short-lived
    installation access token (valid for 1 hour).

    Raises GitHubApiError if the API call fails.
    """
    app = get_app_client()
    try:
        resp = await app.rest.apps.async_create_installation_access_token(
            installation_id
        )
        token: str = resp.parsed_data.token
        logger.info(
            "github_installation_token_exchanged",
            installation_id=installation_id,
        )
        return token
    except Exception as exc:
        raise GitHubApiError(
            f"Failed to get installation access token for installation"
            f" {installation_id}"
        ) from exc


def _reset_app_client() -> None:
    """Reset the singleton app client. For test isolation only."""
    global _app_client
    _app_client = None
