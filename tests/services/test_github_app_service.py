"""Tests for oopsie.services.github_app_service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from githubkit import GitHub
from githubkit.webhooks import sign as webhook_sign
from oopsie.config import Settings
from oopsie.services.exceptions import GitHubApiError, GitHubAppNotConfiguredError
from oopsie.services.github_app_service import (
    _reset_app_client,
    get_app_client,
    get_installation_client,
    get_installation_token,
    list_installation_repos,
    verify_webhook,
)

FAKE_DB_URL = "postgresql+asyncpg://u:p@localhost:5432/db"
FAKE_REDIS_URL = "redis://localhost:6379"

# Reuse the static RSA PEM from test_config — avoids re-generating keys per test.
# fmt: off
VALID_RSA_PEM_B64 = "LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlFb2dJQkFBS0NBUUVBd3A2Q1FobG5mek5SMFBDeFJRSGkvbnlHYkRlS05vSGYrMDNpWEZFcnFjeHVtdnJjCktyWnB6YzdtcXo5cW9NNlBNd0t6YlBoK0Y2L1RTZkJDREZWbm9CQ2hmQTNvcEpTUTA3V2JNSXBBWk8xZEVqVmUKcHdmcUJwbGhTSU03RFMxVEtJek9ZWitBRitZNDVjWCswWkNzbDZUaVJmRTEwVkc0OXRPamwwcnByRHZ1QzMrawpxUFNPemFiYU9WejJ4VEtCWXFhZ2QvOVp0Mlk5SnBiMm1vYUtlbC9pYWZ4RzBpenpMRjhmS1pBRWRxcHVNWG5NCmM5NzdMZGhhTkV1dytNSm52VHNwcUExRTMwSUJ4bHFWbTdxWHprMTZpMnhISzRYaVFMRzdFVkpjWXN4ZkpvcWkKcE1lVlhBU0lPOXZqeVFJTEpGemRaZkZ0SkZxZ3JJOEdzTHlsY3dJREFRQUJBb0lCQUYyWU9FR01rUnI1dGIrYgplVTBjRHF2ZmZCQUFGODZGNEE4dDBnNGVsVGFJRTZzaHVJOHNBYThSOFJuckdoN3lwNmhiQktvRHlUUWdBU2RlClRZMDc1MlZ4aWcrc2FyVDNvN3pFNmpqS1RCU2RtSFJneVQvZnpQcldlWlFUVkd0T1lGOHdkREk3c0RFT0xVL0gKUy9oQnNOY08yeWpTeTFSNmprN1owaU00eWk3akhvZzhFVmEzaTNZY2VrcFZCNThrQ3g4cEdmWm8zR1V1YndZbQpyUzcxWW5QZUtzZ0JqTHFUV2hzaGkwSXAzYjBsREJablE3M0F0M0hGYkMzbUIrakl1NG84cHp2WmJ5N09TeVAwCmpBWVRCekJNMUttQ1p6ak5vUVBhN2ZKSzN3TGtoNktqRVcxYU9BemFvK05ZSjh6VnNDVkxhbC9UbUhQZlVHem8KQlpjZG1EMENnWUVBNkRvTlcyTE1icDFVdDQ2N3JFdGo4Tkxvbm9VRnJPaHlNeStNN09HeTk4OHB3ZHErMFJWRAo0NjhDR002YUxSYVRMTWNwbDJhb3kyV2s5NTlXWGRSaUJNd1pJTmdMZjUzenVZRFBkTFZybU9UZDk3anlMOXlzCnlkcVlHSFFHL0ZhcE1VVG0zZmZuWTRmaDZEMFdEMHlYM1RmRGlNcVVuNUhYUTNkOU5wRW1KQTBDZ1lFQTFvcmcKcVhJa0VDUThMMnViOTQ1aE9NOEgzRFU5WnR0NndhNno4ZmQ2aE5TQ1dPVkZScUJuWjNHcmZCZkpWY1BXSnV1UgpRVDlTMTFRVEo5QXNhS3dWNnNNWDNIdnZGSmoydE0xV1pja01CUS9jNDNieXhNOTQvdW9wOGwzL1c4c01NMVdVCkJzR2RoSi9kbUJ6TEJ2aW04WnBTWms3TzkxV1NkeVVHS1V5RUQzOENnWUFmcFlHYWVZMUlhYkpZelYrdjdCb3oKZ0Zwbzk5RzlMWFFhbTVsRjBzQVQyeXhpbVkrMWFJTjI3S3VKZStZd3pNbkRxV1IybUd2YVJBREdLZldZRmRCQgp2UnFUaWoyTzU1U0dMQktaWWZ2R3V6R3doNGloa3g0TTUvZ2dKUGVxdlppUytVUEk3ZmFmYnE0UGV2dWRuQjk1CjZ4Wi9kclBvUnZTaDRnK3pOdmFPcFFLQmdBNUZDSEpjeENkS3NiSVp2ekwxQm1SbjZNYnR4NXE2eUd4dmVVcUQKd21OcFd3NGNtY0g3MDBUZkc1L1NXVExhSnJsSis4eFNNT2xmanpLYnR3aHpRYlh1cWZ5aFJhS2lGZTZxcGE5NQpjdEkzWHVMR081bDVqenV0U1lMMFc1SzRhNlJTY2RrTk1iUHJpaXFlNTZZY0RjYU9GQ0wzNU80d2crQm0xd1VTCk1NcHpBb0dBZStlbXo2ZjVRY1RwdkF5RzFETjZaSWZXOWJFd1A0YkZkODVlMjUvdERhRzRmUVA3bGpNNnlaTHgKbGNiSld1RVRoemV6UzVxbkJWSVJLMVV5R1B1Zm1EY0xUMnVNZzhqTk5LZ2JvRVNGS2tlSUFpM1FtVVIrcmNRUgpQS2h4Ly81cEdBUmFRZW5sRm9rRlpwdzE5Vml3WXFUUUpwajVnb1hQbHJVQzVRM0dyVEk9Ci0tLS0tRU5EIFJTQSBQUklWQVRFIEtFWS0tLS0tCg=="  # noqa: E501
# fmt: on


@pytest.fixture(autouse=True)
def _reset_client():
    """Reset singleton before and after each test for isolation."""
    _reset_app_client()
    yield
    _reset_app_client()


@pytest.fixture()
def configured_settings():
    """Return a Settings instance with GitHub App credentials configured."""
    return Settings(
        database_url=FAKE_DB_URL,
        redis_url=FAKE_REDIS_URL,
        github_app_id="123",
        github_app_private_key_pem=VALID_RSA_PEM_B64,
    )


def test_get_app_client_returns_github_instance(configured_settings):
    """With valid settings mocked, get_app_client() returns a GitHub instance."""
    with patch(
        "oopsie.services.github_app_service.get_settings",
        return_value=configured_settings,
    ):
        client = get_app_client()
        assert isinstance(client, GitHub)


def test_get_app_client_raises_when_not_configured():
    """With empty github_app_id, raises GitHubAppNotConfiguredError."""
    settings = Settings(
        database_url=FAKE_DB_URL,
        redis_url=FAKE_REDIS_URL,
        github_app_id="",
        github_app_private_key_pem=VALID_RSA_PEM_B64,
    )
    with patch(
        "oopsie.services.github_app_service.get_settings", return_value=settings
    ):
        with pytest.raises(GitHubAppNotConfiguredError):
            get_app_client()


def test_get_app_client_raises_when_no_private_key():
    """With empty github_app_private_key_pem, raises GitHubAppNotConfiguredError."""
    settings = Settings(
        database_url=FAKE_DB_URL,
        redis_url=FAKE_REDIS_URL,
        github_app_id="123",
    )
    with patch(
        "oopsie.services.github_app_service.get_settings", return_value=settings
    ):
        with pytest.raises(GitHubAppNotConfiguredError):
            get_app_client()


def test_get_app_client_singleton(configured_settings):
    """Calling get_app_client() twice returns the same object (identity check)."""
    with patch(
        "oopsie.services.github_app_service.get_settings",
        return_value=configured_settings,
    ):
        client1 = get_app_client()
        client2 = get_app_client()
        assert client1 is client2


def test_get_app_client_reset(configured_settings):
    """After _reset_app_client(), next call creates a new client instance."""
    with patch(
        "oopsie.services.github_app_service.get_settings",
        return_value=configured_settings,
    ):
        client1 = get_app_client()
        _reset_app_client()
        client2 = get_app_client()
        assert client1 is not client2


def test_get_installation_client(configured_settings):
    """get_installation_client returns a GitHub client scoped to the installation."""
    with patch(
        "oopsie.services.github_app_service.get_settings",
        return_value=configured_settings,
    ):
        client = get_installation_client(42)
        assert isinstance(client, GitHub)


@pytest.mark.asyncio
async def test_get_installation_token_returns_string(configured_settings):
    """Mocking the REST call, get_installation_token returns a token string."""
    mock_token_resp = MagicMock()
    mock_token_resp.parsed_data.token = "ghs_test123"

    with patch(
        "oopsie.services.github_app_service.get_settings",
        return_value=configured_settings,
    ):
        app_client = get_app_client()
        with patch.object(
            app_client.rest.apps,
            "async_create_installation_access_token",
            new_callable=AsyncMock,
            return_value=mock_token_resp,
        ):
            token = await get_installation_token(42)
            assert token == "ghs_test123"


@pytest.mark.asyncio
async def test_get_installation_token_raises_on_failure(configured_settings):
    """When REST call raises, get_installation_token wraps it in GitHubApiError."""
    original_error = RuntimeError("API down")

    with patch(
        "oopsie.services.github_app_service.get_settings",
        return_value=configured_settings,
    ):
        app_client = get_app_client()
        with patch.object(
            app_client.rest.apps,
            "async_create_installation_access_token",
            new_callable=AsyncMock,
            side_effect=original_error,
        ):
            with pytest.raises(GitHubApiError) as exc_info:
                await get_installation_token(42)
            assert exc_info.value.__cause__ is original_error


# ---------------------------------------------------------------------------
# verify_webhook tests
# ---------------------------------------------------------------------------

_WEBHOOK_SECRET = "test-webhook-secret"
_WEBHOOK_BODY = b'{"action": "opened", "number": 1}'


def test_verify_webhook_valid_signature():
    """verify_webhook returns True when signature matches the secret and body."""
    sig = webhook_sign(_WEBHOOK_SECRET, _WEBHOOK_BODY)
    assert verify_webhook(_WEBHOOK_SECRET, _WEBHOOK_BODY, sig) is True


def test_verify_webhook_invalid_signature():
    """verify_webhook returns False when the signature is tampered."""
    assert verify_webhook(_WEBHOOK_SECRET, _WEBHOOK_BODY, "sha256=deadbeef") is False


def test_verify_webhook_wrong_secret():
    """verify_webhook returns False when signed with a different secret."""
    sig = webhook_sign("wrong-secret", _WEBHOOK_BODY)
    assert verify_webhook(_WEBHOOK_SECRET, _WEBHOOK_BODY, sig) is False


# ---------------------------------------------------------------------------
# list_installation_repos tests
# ---------------------------------------------------------------------------


def _make_repo(full_name: str) -> MagicMock:
    repo = MagicMock()
    repo.full_name = full_name
    return repo


@pytest.mark.asyncio
async def test_list_installation_repos_returns_full_names(configured_settings):
    """list_installation_repos returns a list of 'owner/repo' strings."""
    mock_resp = MagicMock()
    mock_resp.parsed_data.repositories = [
        _make_repo("acme/api"),
        _make_repo("acme/frontend"),
    ]

    with patch(
        "oopsie.services.github_app_service.get_settings",
        return_value=configured_settings,
    ):
        installation_client = get_installation_client(99)
        with patch(
            "oopsie.services.github_app_service.get_installation_client",
            return_value=installation_client,
        ):
            with patch.object(
                installation_client.rest.apps,
                "async_list_repos_accessible_to_installation",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ):
                repos = await list_installation_repos(99)
                assert repos == ["acme/api", "acme/frontend"]


@pytest.mark.asyncio
async def test_list_installation_repos_empty(configured_settings):
    """list_installation_repos returns an empty list when installation has no repos."""
    mock_resp = MagicMock()
    mock_resp.parsed_data.repositories = []

    with patch(
        "oopsie.services.github_app_service.get_settings",
        return_value=configured_settings,
    ):
        installation_client = get_installation_client(99)
        with patch(
            "oopsie.services.github_app_service.get_installation_client",
            return_value=installation_client,
        ):
            with patch.object(
                installation_client.rest.apps,
                "async_list_repos_accessible_to_installation",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ):
                repos = await list_installation_repos(99)
                assert repos == []


@pytest.mark.asyncio
async def test_list_installation_repos_raises_on_failure(configured_settings):
    """When the REST call raises, list_installation_repos wraps it in GitHubApiError."""
    original_error = RuntimeError("rate limited")

    with patch(
        "oopsie.services.github_app_service.get_settings",
        return_value=configured_settings,
    ):
        installation_client = get_installation_client(99)
        with patch(
            "oopsie.services.github_app_service.get_installation_client",
            return_value=installation_client,
        ):
            with patch.object(
                installation_client.rest.apps,
                "async_list_repos_accessible_to_installation",
                new_callable=AsyncMock,
                side_effect=original_error,
            ):
                with pytest.raises(GitHubApiError) as exc_info:
                    await list_installation_repos(99)
                assert exc_info.value.__cause__ is original_error
