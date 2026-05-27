"""Environment-backed settings for user-facing interfaces."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Final, Literal, Self

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from werewolf_agent.commons.shared.messages import (
    message_game_default_player_count_between,
    message_game_min_players_le_max_players,
)
from werewolf_agent.commons.shared.validation import normalize_choice, normalize_non_blank

APP_NAME: Final = "werewolf-agent"
API_SERVICE_NAME: Final = "werewolf-agent-api"

DEFAULT_GENERATED_DIR: Final = Path(".werewolf-agent")
DEFAULT_SQLITE_PATH: Final = DEFAULT_GENERATED_DIR / "db" / "db.sqlite3"
DEFAULT_LLM_PROVIDER: Final = "dummy"
DEFAULT_LLM_MODEL: Final = "dummy-local"
DEFAULT_LOG_LEVEL: Final = "INFO"
DEFAULT_LOG_FORMAT: Final = "json"
DEFAULT_LOG_OUTPUT: Final = "stderr"
DEFAULT_GAME_MIN_PLAYERS: Final = 5
DEFAULT_GAME_MAX_PLAYERS: Final = 8
DEFAULT_GAME_DEFAULT_PLAYER_COUNT: Final = 6
DEFAULT_GAME_SUPPORTED_AGENT_TYPE: Final = "dummy"
DEFAULT_GAME_SUPPORTED_AGENT_NAME: Final = "Dummy Agent"
DEFAULT_GAME_DEFAULT_RULESET_ID: Final = "default"
DEFAULT_GAME_DEFAULT_RULESET_NAME: Final = "MVP Default"

LOG_LEVEL_NAMES: Final = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
LOG_FORMAT_NAMES: Final = frozenset({"json", "console"})
LOG_OUTPUT_NAMES: Final = frozenset({"stderr", "stdout"})
SUPPORTED_AGENT_TYPE_NAMES: Final = frozenset({DEFAULT_GAME_SUPPORTED_AGENT_TYPE})

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
    """Split a comma-separated setting into clean values."""
    return [item.strip() for item in value.split(",") if item.strip()]


class AppSettings(BaseSettings):
    """Settings loaded by interface entry points and injected inward."""

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

    api_debug: bool = Field(default=True, validation_alias="WEREWOLF_API_DEBUG")
    api_cors_allowed_origins: str = Field(
        default="",
        validation_alias="WEREWOLF_CORS_ALLOWED_ORIGINS",
    )
    sqlite_path: Path = Field(
        default=DEFAULT_SQLITE_PATH,
        validation_alias="WEREWOLF_SQLITE_PATH",
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
    def cors_allowed_origins_list(self) -> list[str]:
        """Return configured CORS origins."""
        return split_csv(self.api_cors_allowed_origins)

    @property
    def sqlite_database_path(self) -> Path:
        """Return an absolute SQLite path, creating parent directories on demand elsewhere."""
        sqlite_path = self.sqlite_path.expanduser()
        if sqlite_path.is_absolute():
            return sqlite_path
        return repository_root() / sqlite_path

    @property
    def configured_database_url(self) -> str:
        """Return the configured database URL without exposing it in repr output."""
        return self.database_url.get_secret_value().strip()

    @property
    def sqlalchemy_database_url(self) -> str:
        """Return a SQLAlchemy database URL, defaulting to local SQLite."""
        database_url = self.configured_database_url
        if database_url:
            if database_url.startswith("postgres://"):
                return database_url.replace("postgres://", "postgresql+psycopg://", 1)
            if database_url.startswith("postgresql://"):
                return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
            return database_url
        return f"sqlite:///{self.sqlite_database_path.as_posix()}"

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

    @field_validator("game_supported_agent_type", mode="before")
    @classmethod
    def normalize_supported_agent_type(cls, value: object) -> str:
        """Return the configured supported agent type."""
        return normalize_choice(
            value,
            field_name="game_supported_agent_type",
            choices=SUPPORTED_AGENT_TYPE_NAMES,
            case="lower",
        )

    @field_validator(
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
            raise ValueError(message_game_min_players_le_max_players())
        if not self.game_min_players <= self.game_default_player_count <= self.game_max_players:
            raise ValueError(message_game_default_player_count_between())
        return self


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached interface settings."""
    return AppSettings()
