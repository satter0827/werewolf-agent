"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Final

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME: Final = "werewolf-agent"
API_SERVICE_NAME: Final = "werewolf-agent-api"
DEFAULT_LLM_PROVIDER: Final = "dummy"
DEFAULT_LLM_MODEL: Final = "dummy-local"
DEFAULT_LOG_LEVEL: Final = "INFO"


@lru_cache(maxsize=1)
def repository_root() -> Path:
    """Return the repository root when running from a source checkout."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def split_csv(value: str) -> list[str]:
    """Split a comma separated environment variable into clean values."""
    return [item.strip() for item in value.split(",") if item.strip()]


class AppSettings(BaseSettings):
    """Environment-backed settings shared by CLI and API entry points."""

    llm_provider: str = Field(
        default=DEFAULT_LLM_PROVIDER,
        validation_alias="WEREWOLF_LLM_PROVIDER",
    )
    model: str = Field(default=DEFAULT_LLM_MODEL, validation_alias="WEREWOLF_MODEL")
    log_level: str = Field(default=DEFAULT_LOG_LEVEL, validation_alias="WEREWOLF_LOG_LEVEL")

    django_secret_key: SecretStr = Field(
        default=SecretStr("django-insecure-local-dev-only"),
        validation_alias=AliasChoices("WEREWOLF_DJANGO_SECRET_KEY", "DJANGO_SECRET_KEY"),
    )
    django_debug: bool = Field(
        default=True,
        validation_alias=AliasChoices("WEREWOLF_DJANGO_DEBUG", "DJANGO_DEBUG"),
    )
    django_allowed_hosts: str = Field(
        default="localhost,127.0.0.1,testserver",
        validation_alias=AliasChoices("WEREWOLF_DJANGO_ALLOWED_HOSTS", "DJANGO_ALLOWED_HOSTS"),
    )
    django_csrf_trusted_origins: str = Field(
        default="",
        validation_alias=AliasChoices(
            "WEREWOLF_DJANGO_CSRF_TRUSTED_ORIGINS",
            "DJANGO_CSRF_TRUSTED_ORIGINS",
        ),
    )
    django_language_code: str = Field(
        default="ja",
        validation_alias=AliasChoices("WEREWOLF_DJANGO_LANGUAGE_CODE", "DJANGO_LANGUAGE_CODE"),
    )
    django_time_zone: str = Field(
        default="Asia/Tokyo",
        validation_alias=AliasChoices("WEREWOLF_DJANGO_TIME_ZONE", "DJANGO_TIME_ZONE", "TZ"),
    )
    django_sqlite_path: Path = Field(
        default=Path("backend/db.sqlite3"),
        validation_alias=AliasChoices("WEREWOLF_DJANGO_SQLITE_PATH", "DJANGO_SQLITE_PATH"),
    )

    model_config = SettingsConfigDict(
        env_file=repository_root() / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def django_allowed_hosts_list(self) -> list[str]:
        """Return configured Django hosts as a list."""
        return split_csv(self.django_allowed_hosts)

    @property
    def django_csrf_trusted_origins_list(self) -> list[str]:
        """Return configured CSRF trusted origins as a list."""
        return split_csv(self.django_csrf_trusted_origins)

    @property
    def django_sqlite_database(self) -> Path:
        """Return an absolute SQLite database path."""
        sqlite_path = self.django_sqlite_path.expanduser()
        if sqlite_path.is_absolute():
            return sqlite_path
        return repository_root() / sqlite_path


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached application settings."""
    return AppSettings()
