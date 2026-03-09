"""Tests for application config."""

from oopsie.config import Settings

FAKE_DB_URL = "postgresql+asyncpg://u:p@localhost:5432/db"
FAKE_REDIS_URL = "redis://localhost:6379"


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
