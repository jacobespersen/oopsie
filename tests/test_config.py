"""Tests for application config."""

from oopsie.config import Settings

FAKE_DB_URL = "postgresql+asyncpg://u:p@localhost:5432/db"
FAKE_REDIS_URL = "redis://localhost:6379"

# Static base64-encoded RSA 2048 private key generated once for tests.
# Avoids slow key generation per test while keeping tests hermetic.
# fmt: off
VALID_RSA_PEM_B64 = "LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlFb2dJQkFBS0NBUUVBd3A2Q1FobG5mek5SMFBDeFJRSGkvbnlHYkRlS05vSGYrMDNpWEZFcnFjeHVtdnJjCktyWnB6YzdtcXo5cW9NNlBNd0t6YlBoK0Y2L1RTZkJDREZWbm9CQ2hmQTNvcEpTUTA3V2JNSXBBWk8xZEVqVmUKcHdmcUJwbGhTSU03RFMxVEtJek9ZWitBRitZNDVjWCswWkNzbDZUaVJmRTEwVkc0OXRPamwwcnByRHZ1QzMrawpxUFNPemFiYU9WejJ4VEtCWXFhZ2QvOVp0Mlk5SnBiMm1vYUtlbC9pYWZ4RzBpenpMRjhmS1pBRWRxcHVNWG5NCmM5NzdMZGhhTkV1dytNSm52VHNwcUExRTMwSUJ4bHFWbTdxWHprMTZpMnhISzRYaVFMRzdFVkpjWXN4ZkpvcWkKcE1lVlhBU0lPOXZqeVFJTEpGemRaZkZ0SkZxZ3JJOEdzTHlsY3dJREFRQUJBb0lCQUYyWU9FR01rUnI1dGIrYgplVTBjRHF2ZmZCQUFGODZGNEE4dDBnNGVsVGFJRTZzaHVJOHNBYThSOFJuckdoN3lwNmhiQktvRHlUUWdBU2RlClRZMDc1MlZ4aWcrc2FyVDNvN3pFNmpqS1RCU2RtSFJneVQvZnpQcldlWlFUVkd0T1lGOHdkREk3c0RFT0xVL0gKUy9oQnNOY08yeWpTeTFSNmprN1owaU00eWk3akhvZzhFVmEzaTNZY2VrcFZCNThrQ3g4cEdmWm8zR1V1YndZbQpyUzcxWW5QZUtzZ0JqTHFUV2hzaGkwSXAzYjBsREJablE3M0F0M0hGYkMzbUIrakl1NG84cHp2WmJ5N09TeVAwCmpBWVRCekJNMUttQ1p6ak5vUVBhN2ZKSzN3TGtoNktqRVcxYU9BemFvK05ZSjh6VnNDVkxhbC9UbUhQZlVHem8KQlpjZG1EMENnWUVBNkRvTlcyTE1icDFVdDQ2N3JFdGo4Tkxvbm9VRnJPaHlNeStNN09HeTk4OHB3ZHErMFJWRAo0NjhDR002YUxSYVRMTWNwbDJhb3kyV2s5NTlXWGRSaUJNd1pJTmdMZjUzenVZRFBkTFZybU9UZDk3anlMOXlzCnlkcVlHSFFHL0ZhcE1VVG0zZmZuWTRmaDZEMFdEMHlYM1RmRGlNcVVuNUhYUTNkOU5wRW1KQTBDZ1lFQTFvcmcKcVhJa0VDUThMMnViOTQ1aE9NOEgzRFU5WnR0NndhNno4ZmQ2aE5TQ1dPVkZScUJuWjNHcmZCZkpWY1BXSnV1UgpRVDlTMTFRVEo5QXNhS3dWNnNNWDNIdnZGSmoydE0xV1pja01CUS9jNDNieXhNOTQvdW9wOGwzL1c4c01NMVdVCkJzR2RoSi9kbUJ6TEJ2aW04WnBTWms3TzkxV1NkeVVHS1V5RUQzOENnWUFmcFlHYWVZMUlhYkpZelYrdjdCb3oKZ0Zwbzk5RzlMWFFhbTVsRjBzQVQyeXhpbVkrMWFJTjI3S3VKZStZd3pNbkRxV1IybUd2YVJBREdLZldZRmRCQgp2UnFUaWoyTzU1U0dMQktaWWZ2R3V6R3doNGloa3g0TTUvZ2dKUGVxdlppUytVUEk3ZmFmYnE0UGV2dWRuQjk1CjZ4Wi9kclBvUnZTaDRnK3pOdmFPcFFLQmdBNUZDSEpjeENkS3NiSVp2ekwxQm1SbjZNYnR4NXE2eUd4dmVVcUQKd21OcFd3NGNtY0g3MDBUZkc1L1NXVExhSnJsSis4eFNNT2xmanpLYnR3aHpRYlh1cWZ5aFJhS2lGZTZxcGE5NQpjdEkzWHVMR081bDVqenV0U1lMMFc1SzRhNlJTY2RrTk1iUHJpaXFlNTZZY0RjYU9GQ0wzNU80d2crQm0xd1VTCk1NcHpBb0dBZStlbXo2ZjVRY1RwdkF5RzFETjZaSWZXOWJFd1A0YkZkODVlMjUvdERhRzRmUVA3bGpNNnlaTHgKbGNiSld1RVRoemV6UzVxbkJWSVJLMVV5R1B1Zm1EY0xUMnVNZzhqTk5LZ2JvRVNGS2tlSUFpM1FtVVIrcmNRUgpQS2h4Ly81cEdBUmFRZW5sRm9rRlpwdzE5Vml3WXFUUUpwajVnb1hQbHJVQzVRM0dyVEk9Ci0tLS0tRU5EIFJTQSBQUklWQVRFIEtFWS0tLS0tCg=="  # noqa: E501
# fmt: on


def test_get_test_database_url_uses_test_database_url_when_set():
    """When test_database_url is set, return it."""
    settings = Settings(
        database_url="postgresql+asyncpg://a:b@localhost:5432/main_db",
        redis_url=FAKE_REDIS_URL,
        test_database_url="postgresql+asyncpg://a:b@localhost:5434/oopsie_test",
    )
    assert settings.get_test_database_url() == (
        "postgresql+asyncpg://a:b@localhost:5434/oopsie_test"
    )


def test_get_test_database_url_derives_from_database_url_when_test_not_set():
    """When test_database_url is None, derive URL from database_url as oopsie_test."""
    settings = Settings(
        database_url="postgresql+asyncpg://u:p@host:5432/myapp",
        redis_url=FAKE_REDIS_URL,
        test_database_url=None,
    )
    url = settings.get_test_database_url()
    assert url == "postgresql+asyncpg://u:p@host:5432/oopsie_test"


def test_worker_settings_defaults():
    """Worker-related settings have sensible defaults."""
    settings = Settings(
        database_url=FAKE_DB_URL,
        redis_url=FAKE_REDIS_URL,
    )
    assert settings.worker_concurrency == 3
    assert settings.job_timeout_seconds == 600
    assert settings.clone_base_path.endswith("oopsie-clones")


def test_github_app_private_key_valid():
    """Settings with a valid base64-encoded RSA PEM key constructs without error."""
    settings = Settings(
        database_url=FAKE_DB_URL,
        redis_url=FAKE_REDIS_URL,
        github_app_private_key_pem=VALID_RSA_PEM_B64,
    )
    result = settings.github_app_private_key_bytes
    assert result is not None
    assert isinstance(result, bytes)
    assert b"PRIVATE KEY" in result


def test_github_app_private_key_invalid_raises():
    """Settings with invalid base64/PEM raises ValueError matching the field name."""
    import pytest

    with pytest.raises(ValueError, match="GITHUB_APP_PRIVATE_KEY_PEM"):
        Settings(
            database_url=FAKE_DB_URL,
            redis_url=FAKE_REDIS_URL,
            github_app_private_key_pem="not-valid-base64!!!",
        )


def test_github_app_private_key_empty_no_error():
    """Settings without PEM field constructs without error; property returns None."""
    settings = Settings(
        database_url=FAKE_DB_URL,
        redis_url=FAKE_REDIS_URL,
    )
    assert settings.github_app_private_key_bytes is None


def test_github_app_fields_default_empty():
    """github_app_id and github_webhook_secret default to empty string."""
    settings = Settings(
        database_url=FAKE_DB_URL,
        redis_url=FAKE_REDIS_URL,
    )
    assert settings.github_app_id == ""
    assert settings.github_webhook_secret == ""
