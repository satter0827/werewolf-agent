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
    message_mapping_item_must_use_separator,
    message_ruleset_description_template_invalid,
)
from werewolf_agent.commons.shared.validation import normalize_choice, normalize_non_blank

APP_NAME: Final = "werewolf-agent"
API_SERVICE_NAME: Final = "werewolf-agent-api"

DEFAULT_GENERATED_DIR: Final = Path(".werewolf-agent")
DEFAULT_SQLITE_PATH: Final = DEFAULT_GENERATED_DIR / "db" / "db.sqlite3"
DEFAULT_LLM_PROVIDER: Final = "fake_llm"
DEFAULT_LLM_MODEL: Final = "fake-llm-local"
DEFAULT_LLM_TIMEOUT_SECONDS: Final = 30.0
DEFAULT_LLM_MAX_RETRIES: Final = 2
DEFAULT_LLM_TEMPERATURE: Final = 0.7
DEFAULT_FAKE_LLM_STRATEGY: Final = "seeded"
DEFAULT_FAKE_LLM_RANDOMNESS: Final = 0.7
DEFAULT_FAKE_LLM_SPEECH_TEMPLATES: Final = (
    "I want to hear more from {target_name}.|"
    "{target_name}'s vote history looks worth checking.|"
    "I will compare today's claims before voting."
)
DEFAULT_LOG_LEVEL: Final = "INFO"
DEFAULT_LOG_FORMAT: Final = "json"
DEFAULT_LOG_OUTPUT: Final = "stderr"
DEFAULT_CLI_API_URL: Final = "http://127.0.0.1:8000/api/v1"
DEFAULT_CLI_HTTP_TIMEOUT_SECONDS: Final = 10.0
DEFAULT_CLI_MAX_STEPS: Final = 64
DEFAULT_CLI_POLL_INTERVAL_SECONDS: Final = 0.0
DEFAULT_CLI_EVENT_LIMIT: Final = 100
DEFAULT_CLI_OUTPUT_FORMAT: Final = "table"
DEFAULT_API_TITLE: Final = "Werewolf Agent API"
DEFAULT_API_VERSION: Final = "0.1.0"
DEFAULT_API_DEBUG: Final = False
DEFAULT_API_CORS_ALLOWED_ORIGINS: Final = ""
DEFAULT_API_CORS_ALLOWED_METHODS: Final = "GET,POST"
DEFAULT_API_CORS_ALLOWED_HEADERS: Final = "*"
DEFAULT_GAME_MIN_PLAYERS: Final = 5
DEFAULT_GAME_MAX_PLAYERS: Final = 8
DEFAULT_GAME_DEFAULT_PLAYER_COUNT: Final = 6
DEFAULT_GAME_SUPPORTED_AGENT_TYPE: Final = "llm"
DEFAULT_GAME_SUPPORTED_AGENT_NAME: Final = "LLM Agent"
DEFAULT_GAME_DEFAULT_RULESET_ID: Final = "default"
DEFAULT_GAME_DEFAULT_RULESET_NAME: Final = "MVP Default"
DEFAULT_GAME_RULESET_DESCRIPTION_TEMPLATE: Final = (
    "{min_players}〜{max_players}人向けの最小同期 API ルールセットです。"
)
DEFAULT_GAME_ROLE_NAMES: Final = "villager:村人,werewolf:人狼,seer:占い師,knight:騎士"
DEFAULT_GAME_PHASE_NAMES: Final = "night:夜,day_discussion:昼チャット,voting:投票,finished:終了"

LOG_LEVEL_NAMES: Final = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
LOG_FORMAT_NAMES: Final = frozenset({"json", "console"})
LOG_OUTPUT_NAMES: Final = frozenset({"stderr", "stdout"})
CLI_OUTPUT_FORMAT_NAMES: Final = frozenset({"table", "json", "jsonl"})
LLM_PROVIDER_NAMES: Final = frozenset({DEFAULT_LLM_PROVIDER})
FAKE_LLM_STRATEGY_NAMES: Final = frozenset({"seeded", "random"})
SUPPORTED_AGENT_TYPE_NAMES: Final = frozenset({DEFAULT_GAME_SUPPORTED_AGENT_TYPE})

LogFormat = Literal["json", "console"]
LogOutput = Literal["stderr", "stdout"]
CliOutputFormat = Literal["table", "json", "jsonl"]


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


def split_mapping(value: str, *, field_name: str) -> dict[str, str]:
    """Split a comma-separated key:value setting into a mapping."""
    mapping: dict[str, str] = {}
    for item in split_csv(value):
        key, separator, item_value = item.partition(":")
        if separator == "":
            raise ValueError(message_mapping_item_must_use_separator(field_name, ":"))
        key = key.strip()
        item_value = item_value.strip()
        if not key or not item_value:
            raise ValueError(message_mapping_item_must_use_separator(field_name, ":"))
        mapping[key] = item_value
    return mapping


class AppSettings(BaseSettings):
    """Settings loaded by interface entry points and injected inward."""

    llm_provider: str = Field(
        default=DEFAULT_LLM_PROVIDER,
        validation_alias="WEREWOLF_LLM_PROVIDER",
    )
    model: str = Field(default=DEFAULT_LLM_MODEL, validation_alias="WEREWOLF_MODEL")
    llm_timeout_seconds: float = Field(
        default=DEFAULT_LLM_TIMEOUT_SECONDS,
        gt=0,
        validation_alias="WEREWOLF_LLM_TIMEOUT_SECONDS",
    )
    llm_max_retries: int = Field(
        default=DEFAULT_LLM_MAX_RETRIES,
        ge=0,
        validation_alias="WEREWOLF_LLM_MAX_RETRIES",
    )
    llm_temperature: float = Field(
        default=DEFAULT_LLM_TEMPERATURE,
        ge=0,
        le=2,
        validation_alias="WEREWOLF_LLM_TEMPERATURE",
    )
    fake_llm_strategy: str = Field(
        default=DEFAULT_FAKE_LLM_STRATEGY,
        validation_alias="WEREWOLF_FAKE_LLM_STRATEGY",
    )
    fake_llm_randomness: float = Field(
        default=DEFAULT_FAKE_LLM_RANDOMNESS,
        ge=0,
        le=1,
        validation_alias="WEREWOLF_FAKE_LLM_RANDOMNESS",
    )
    fake_llm_speech_templates: str = Field(
        default=DEFAULT_FAKE_LLM_SPEECH_TEMPLATES,
        validation_alias="WEREWOLF_FAKE_LLM_SPEECH_TEMPLATES",
    )
    log_level: str = Field(default=DEFAULT_LOG_LEVEL, validation_alias="WEREWOLF_LOG_LEVEL")
    log_format: LogFormat = Field(
        default=DEFAULT_LOG_FORMAT,
        validation_alias="WEREWOLF_LOG_FORMAT",
    )
    log_output: LogOutput = Field(
        default=DEFAULT_LOG_OUTPUT,
        validation_alias="WEREWOLF_LOG_OUTPUT",
    )
    cli_api_url: str = Field(
        default=DEFAULT_CLI_API_URL,
        validation_alias="WEREWOLF_CLI_API_URL",
    )
    cli_http_timeout_seconds: float = Field(
        default=DEFAULT_CLI_HTTP_TIMEOUT_SECONDS,
        gt=0,
        validation_alias="WEREWOLF_CLI_HTTP_TIMEOUT_SECONDS",
    )
    cli_max_steps: int = Field(
        default=DEFAULT_CLI_MAX_STEPS,
        ge=1,
        validation_alias="WEREWOLF_CLI_MAX_STEPS",
    )
    cli_poll_interval_seconds: float = Field(
        default=DEFAULT_CLI_POLL_INTERVAL_SECONDS,
        ge=0,
        validation_alias="WEREWOLF_CLI_POLL_INTERVAL_SECONDS",
    )
    cli_event_limit: int = Field(
        default=DEFAULT_CLI_EVENT_LIMIT,
        ge=1,
        le=500,
        validation_alias="WEREWOLF_CLI_EVENT_LIMIT",
    )
    cli_output_format: CliOutputFormat = Field(
        default=DEFAULT_CLI_OUTPUT_FORMAT,
        validation_alias="WEREWOLF_CLI_OUTPUT_FORMAT",
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
    game_ruleset_description_template: str = Field(
        default=DEFAULT_GAME_RULESET_DESCRIPTION_TEMPLATE,
        validation_alias="WEREWOLF_GAME_RULESET_DESCRIPTION_TEMPLATE",
    )
    game_role_names: str = Field(
        default=DEFAULT_GAME_ROLE_NAMES,
        validation_alias="WEREWOLF_GAME_ROLE_NAMES",
    )
    game_phase_names: str = Field(
        default=DEFAULT_GAME_PHASE_NAMES,
        validation_alias="WEREWOLF_GAME_PHASE_NAMES",
    )

    api_title: str = Field(default=DEFAULT_API_TITLE, validation_alias="WEREWOLF_API_TITLE")
    api_version: str = Field(default=DEFAULT_API_VERSION, validation_alias="WEREWOLF_API_VERSION")
    api_debug: bool = Field(default=DEFAULT_API_DEBUG, validation_alias="WEREWOLF_API_DEBUG")
    api_cors_allowed_origins: str = Field(
        default=DEFAULT_API_CORS_ALLOWED_ORIGINS,
        validation_alias="WEREWOLF_CORS_ALLOWED_ORIGINS",
    )
    api_cors_allowed_methods: str = Field(
        default=DEFAULT_API_CORS_ALLOWED_METHODS,
        validation_alias="WEREWOLF_CORS_ALLOWED_METHODS",
    )
    api_cors_allowed_headers: str = Field(
        default=DEFAULT_API_CORS_ALLOWED_HEADERS,
        validation_alias="WEREWOLF_CORS_ALLOWED_HEADERS",
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
    def cors_allowed_methods_list(self) -> list[str]:
        """Return configured CORS methods."""
        return split_csv(self.api_cors_allowed_methods)

    @property
    def cors_allowed_headers_list(self) -> list[str]:
        """Return configured CORS headers."""
        return split_csv(self.api_cors_allowed_headers)

    @property
    def game_role_name_map(self) -> dict[str, str]:
        """Return configured public role display names."""
        return split_mapping(self.game_role_names, field_name="game_role_names")

    @property
    def game_phase_name_map(self) -> dict[str, str]:
        """Return configured public phase display names."""
        return split_mapping(self.game_phase_names, field_name="game_phase_names")

    @property
    def fake_llm_speech_template_list(self) -> list[str]:
        """Return configured FakeLLM speech templates."""
        return [item.strip() for item in self.fake_llm_speech_templates.split("|") if item.strip()]

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

    @field_validator("cli_output_format", mode="before")
    @classmethod
    def normalize_cli_output_format(cls, value: object) -> str:
        """Return a validated lowercase CLI output format name."""
        return normalize_choice(
            value,
            field_name="cli_output_format",
            choices=CLI_OUTPUT_FORMAT_NAMES,
            case="lower",
        )

    @field_validator("llm_provider", mode="before")
    @classmethod
    def normalize_llm_provider(cls, value: object) -> str:
        """Return the configured LLM provider."""
        return normalize_choice(
            value,
            field_name="llm_provider",
            choices=LLM_PROVIDER_NAMES,
            case="lower",
        )

    @field_validator("fake_llm_strategy", mode="before")
    @classmethod
    def normalize_fake_llm_strategy(cls, value: object) -> str:
        """Return the configured FakeLLM strategy."""
        return normalize_choice(
            value,
            field_name="fake_llm_strategy",
            choices=FAKE_LLM_STRATEGY_NAMES,
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
        "game_ruleset_description_template",
        "game_role_names",
        "game_phase_names",
        "fake_llm_speech_templates",
        "api_title",
        "api_version",
        "cli_api_url",
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
        split_mapping(self.game_role_names, field_name="game_role_names")
        split_mapping(self.game_phase_names, field_name="game_phase_names")
        if not self.fake_llm_speech_template_list:
            raise ValueError("fake_llm_speech_templates must include at least one template")
        try:
            self.game_ruleset_description_template.format(
                min_players=self.game_min_players,
                max_players=self.game_max_players,
                default_player_count=self.game_default_player_count,
            )
        except (KeyError, ValueError) as exc:
            raise ValueError(message_ruleset_description_template_invalid()) from exc
        return self


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached interface settings."""
    return AppSettings()
