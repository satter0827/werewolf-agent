"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from importlib import import_module
from pathlib import Path
from typing import Any, Final, Literal, Self, cast

from pydantic import AliasChoices, Field, SecretStr
from pydantic.functional_validators import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from werewolf_agent.commons.configuration.defaults import (
    DEFAULT_DJANGO_SECRET_KEY,
    DEFAULT_DJANGO_SQLITE_PATH,
    DEFAULT_GAME_DEFAULT_PLAYER_COUNT,
    DEFAULT_GAME_DEFAULT_RULESET_ID,
    DEFAULT_GAME_DEFAULT_RULESET_NAME,
    DEFAULT_GAME_MAX_PLAYERS,
    DEFAULT_GAME_MIN_PLAYERS,
    DEFAULT_GAME_SUPPORTED_AGENT_NAME,
    DEFAULT_GAME_SUPPORTED_AGENT_TYPE,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_LOG_FORMAT,
    DEFAULT_LOG_LEVEL,
    DEFAULT_LOG_OUTPUT,
    MIN_DJANGO_SECRET_KEY_LENGTH,
)

LOG_LEVEL_NAMES: Final = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
LOG_FORMAT_NAMES: Final = frozenset({"json", "console"})
LOG_OUTPUT_NAMES: Final = frozenset({"stderr", "stdout"})

LogFormat = Literal["json", "console"]
LogOutput = Literal["stderr", "stdout"]


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


def normalize_choice(
    value: object,
    *,
    field_name: str,
    choices: frozenset[str],
    case: Literal["upper", "lower"],
) -> str:
    """Return a validated string choice normalized to the configured case."""
    if not isinstance(value, str):
        msg = f"{field_name} must be a string"
        raise ValueError(msg)

    normalized = value.strip().upper() if case == "upper" else value.strip().lower()
    if normalized not in choices:
        msg = f"{field_name} must be one of: {', '.join(sorted(choices))}"
        raise ValueError(msg)
    return normalized


def normalize_non_blank(value: object, *, field_name: str) -> str:
    """Return a stripped non-empty string."""
    if not isinstance(value, str):
        msg = f"{field_name} must be a string"
        raise ValueError(msg)
    normalized = value.strip()
    if not normalized:
        msg = f"{field_name} must not be blank"
        raise ValueError(msg)
    return normalized


class AppSettings(BaseSettings):
    """Environment-backed settings shared by CLI and API entry points."""

    llm_provider: str = Field(
        default=DEFAULT_LLM_PROVIDER,
        validation_alias="WEREWOLF_LLM_PROVIDER",
    )
    model: str = Field(default=DEFAULT_LLM_MODEL, validation_alias="WEREWOLF_MODEL")
    log_level: str = Field(default=DEFAULT_LOG_LEVEL, validation_alias="WEREWOLF_LOG_LEVEL")
    log_format: LogFormat = Field(
        default=DEFAULT_LOG_FORMAT,
        validation_alias="WEREWOLF_LOG_FORMAT",
    )
    log_output: LogOutput = Field(
        default=DEFAULT_LOG_OUTPUT,
        validation_alias="WEREWOLF_LOG_OUTPUT",
    )

    game_min_players: int = Field(
        default=DEFAULT_GAME_MIN_PLAYERS,
        ge=1,
        validation_alias="WEREWOLF_GAME_MIN_PLAYERS",
    )
    game_max_players: int = Field(
        default=DEFAULT_GAME_MAX_PLAYERS,
        ge=1,
        validation_alias="WEREWOLF_GAME_MAX_PLAYERS",
    )
    game_default_player_count: int = Field(
        default=DEFAULT_GAME_DEFAULT_PLAYER_COUNT,
        ge=1,
        validation_alias="WEREWOLF_GAME_DEFAULT_PLAYER_COUNT",
    )
    game_supported_agent_type: str = Field(
        default=DEFAULT_GAME_SUPPORTED_AGENT_TYPE,
        validation_alias="WEREWOLF_GAME_SUPPORTED_AGENT_TYPE",
    )
    game_supported_agent_name: str = Field(
        default=DEFAULT_GAME_SUPPORTED_AGENT_NAME,
        validation_alias="WEREWOLF_GAME_SUPPORTED_AGENT_NAME",
    )
    game_default_ruleset_id: str = Field(
        default=DEFAULT_GAME_DEFAULT_RULESET_ID,
        validation_alias="WEREWOLF_GAME_DEFAULT_RULESET_ID",
    )
    game_default_ruleset_name: str = Field(
        default=DEFAULT_GAME_DEFAULT_RULESET_NAME,
        validation_alias="WEREWOLF_GAME_DEFAULT_RULESET_NAME",
    )

    django_secret_key: SecretStr = Field(
        default=SecretStr(DEFAULT_DJANGO_SECRET_KEY),
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
        default=DEFAULT_DJANGO_SQLITE_PATH,
        validation_alias=AliasChoices("WEREWOLF_DJANGO_SQLITE_PATH", "DJANGO_SQLITE_PATH"),
    )
    database_url: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("WEREWOLF_DATABASE_URL", "DATABASE_URL"),
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

    @property
    def django_database_url(self) -> str:
        """Return the configured database URL without exposing it in repr output."""
        return self.database_url.get_secret_value().strip()

    @property
    def django_database_config(self) -> dict[str, Any]:
        """Return Django DATABASES['default'] for SQLite or DATABASE_URL deployments."""
        database_url = self.django_database_url
        if database_url:
            database_parser = import_module("dj_database_url")
            return cast(
                "dict[str, Any]",
                database_parser.parse(
                    database_url,
                    conn_max_age=600,
                    conn_health_checks=True,
                ),
            )

        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": self.django_sqlite_database,
        }

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> str:
        """Return a validated uppercase logging level name."""
        return normalize_choice(
            value,
            field_name="log_level",
            choices=LOG_LEVEL_NAMES,
            case="upper",
        )

    @field_validator("log_format", mode="before")
    @classmethod
    def normalize_log_format(cls, value: object) -> str:
        """Return a validated lowercase logging formatter name."""
        return normalize_choice(
            value,
            field_name="log_format",
            choices=LOG_FORMAT_NAMES,
            case="lower",
        )

    @field_validator("log_output", mode="before")
    @classmethod
    def normalize_log_output(cls, value: object) -> str:
        """Return a validated lowercase logging stream name."""
        return normalize_choice(
            value,
            field_name="log_output",
            choices=LOG_OUTPUT_NAMES,
            case="lower",
        )

    @field_validator(
        "game_supported_agent_type",
        "game_supported_agent_name",
        "game_default_ruleset_id",
        "game_default_ruleset_name",
        mode="before",
    )
    @classmethod
    def normalize_game_text(cls, value: object) -> str:
        """Return a stripped non-empty game configuration string."""
        return normalize_non_blank(value, field_name="game setting")

    @model_validator(mode="after")
    def validate_game_settings(self) -> Self:
        """Ensure game count defaults are internally consistent."""
        if self.game_min_players > self.game_max_players:
            msg = "game_min_players must be less than or equal to game_max_players"
            raise ValueError(msg)
        if not self.game_min_players <= self.game_default_player_count <= self.game_max_players:
            msg = "game_default_player_count must be between game_min_players and game_max_players"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def validate_django_secret_key(self) -> Self:
        """Require an explicit Django secret key for non-debug deployments."""
        secret_key = self.django_secret_key.get_secret_value().strip()
        if not secret_key:
            msg = "django_secret_key must not be blank"
            raise ValueError(msg)
        if not self.django_debug and secret_key == DEFAULT_DJANGO_SECRET_KEY:
            msg = "WEREWOLF_DJANGO_SECRET_KEY must be set when WEREWOLF_DJANGO_DEBUG is false"
            raise ValueError(msg)
        if not self.django_debug and len(secret_key) < MIN_DJANGO_SECRET_KEY_LENGTH:
            msg = (
                "WEREWOLF_DJANGO_SECRET_KEY must be at least "
                f"{MIN_DJANGO_SECRET_KEY_LENGTH} characters when WEREWOLF_DJANGO_DEBUG is false"
            )
            raise ValueError(msg)
        return self


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached application settings."""
    return AppSettings()
