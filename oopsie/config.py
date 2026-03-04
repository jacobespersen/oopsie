"""Application settings via pydantic-settings."""

import warnings
from functools import lru_cache
from urllib.parse import urlparse, urlunparse

from cryptography.fernet import Fernet
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    test_database_url: str | None = None
    encryption_key: str = ""
    anthropic_api_key: str = ""
    log_level: str = "INFO"
    log_format: str = "json"
    redis_url: str = ""
    worker_concurrency: int = 3
    job_timeout_seconds: int = 600
    clone_base_path: str = "/tmp/oopsie-clones"

    @model_validator(mode="after")
    def _validate_encryption_key(self) -> "Settings":
        if not self.encryption_key:
            warnings.warn(
                "ENCRYPTION_KEY is not set. "
                "Creating or updating projects with GitHub tokens will fail.",
                UserWarning,
                stacklevel=2,
            )
        else:
            try:
                Fernet(self.encryption_key.encode("utf-8"))
            except Exception as exc:
                raise ValueError(
                    "ENCRYPTION_KEY is not a valid Fernet key. "
                    "Generate one with: python -c "
                    "'from cryptography.fernet import Fernet; "
                    "print(Fernet.generate_key().decode())'"
                ) from exc
        return self

    def get_test_database_url(self) -> str:
        """Return test DB URL (test_database_url or database_url, db oopsie_test)."""
        if self.test_database_url:
            return self.test_database_url
        parsed = urlparse(self.database_url)
        path = parsed.path.rstrip("/")
        parts = path.split("/")
        parts[-1] = "oopsie_test"
        new_path = "/".join(parts)
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                new_path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (created once per process)."""
    return Settings()
