"""Environment-backed settings for user-facing interfaces."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Final, Literal, Self, cast

from pydantic import (
    AliasChoices,
    Field,
    SecretStr,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from werewolf_agent.commons.shared.messages import (
    message_game_default_player_count_between,
    message_game_min_players_le_max_players,
    message_mapping_item_must_use_separator,
    message_ruleset_description_template_invalid,
)
from werewolf_agent.commons.shared.validation import normalize_choice, normalize_non_blank

DEFAULTS_PACKAGE: Final = "werewolf_agent.resources.settings"
DEFAULTS_FILE: Final = "defaults.toml"


def _load_packaged_defaults() -> Mapping[str, object]:
    default_path = files(DEFAULTS_PACKAGE).joinpath(DEFAULTS_FILE)
    with default_path.open("rb") as default_file:
        return tomllib.load(default_file)


PACKAGED_DEFAULTS = _load_packaged_defaults()


def _default_value(key: str) -> object:
    try:
        return PACKAGED_DEFAULTS[key]
    except KeyError as exc:
        raise RuntimeError(f"Missing default setting: {key}") from exc


def _string_default(key: str) -> str:
    return str(_default_value(key))


def _integer_default(key: str) -> int:
    value = _default_value(key)
    if isinstance(value, int):
        return value
    return int(str(value))


def _float_default(key: str) -> float:
    value = _default_value(key)
    if isinstance(value, (float, int)):
        return float(value)
    return float(str(value))


def _bool_default(key: str) -> bool:
    value = _default_value(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _path_default(key: str) -> Path:
    return Path(_string_default(key))


APP_NAME: Final = _string_default("app_name")
DEFAULT_API_SERVICE_NAME: Final = _string_default("api_service_name")

DEFAULT_GENERATED_DIR: Final = _path_default("generated_dir")
DEFAULT_SQLITE_PATH: Final = _path_default("sqlite_path")
DEFAULT_LLM_PROVIDER: Final = _string_default("llm_provider")
DEFAULT_LLM_MODEL: Final = _string_default("model")
DEFAULT_LLM_TIMEOUT_SECONDS: Final = _float_default("llm_timeout_seconds")
DEFAULT_LLM_MAX_RETRIES: Final = _integer_default("llm_max_retries")
DEFAULT_LLM_TEMPERATURE: Final = _float_default("llm_temperature")
DEFAULT_LLM_PROMPT_FILE: Final = _string_default("llm_prompt_file")
DEFAULT_LLM_FAKE_RESPONSES_FILE: Final = _string_default("llm_fake_responses_file")
DEFAULT_LOG_LEVEL: Final = _string_default("log_level")
DEFAULT_LOG_OUTPUT: Final = _string_default("log_output")
DEFAULT_LOG_DIR: Final = _path_default("log_dir")
DEFAULT_LOG_FILE_NAME: Final = _string_default("log_file_name")
DEFAULT_LOG_RETENTION_DAYS: Final = _integer_default("log_retention_days")
DEFAULT_LOG_THIRD_PARTY_LEVEL: Final = _string_default("log_third_party_level")
DEFAULT_CLI_API_URL: Final = _string_default("cli_api_url")
DEFAULT_CLI_HTTP_TIMEOUT_SECONDS: Final = _float_default("cli_http_timeout_seconds")
DEFAULT_CLI_MAX_STEPS: Final = _integer_default("cli_max_steps")
DEFAULT_CLI_POLL_INTERVAL_SECONDS: Final = _float_default("cli_poll_interval_seconds")
DEFAULT_CLI_EVENT_LIMIT: Final = _integer_default("cli_event_limit")
DEFAULT_CLI_OUTPUT_FORMAT: Final = _string_default("cli_output_format")
DEFAULT_STREAMLIT_API_URL: Final = _string_default("streamlit_api_url")
DEFAULT_STREAMLIT_HTTP_TIMEOUT_SECONDS: Final = _float_default("streamlit_http_timeout_seconds")
DEFAULT_STREAMLIT_REFRESH_INTERVAL_SECONDS: Final = _float_default(
    "streamlit_refresh_interval_seconds"
)
DEFAULT_STREAMLIT_EVENT_LIMIT: Final = _integer_default("streamlit_event_limit")
DEFAULT_STREAMLIT_TURN_LIMIT: Final = _integer_default("streamlit_turn_limit")
DEFAULT_STREAMLIT_RUN_LIMIT: Final = _integer_default("streamlit_run_limit")
DEFAULT_STREAMLIT_MAX_AUTO_STEPS: Final = _integer_default("streamlit_max_auto_steps")
DEFAULT_STREAMLIT_LANGUAGE: Final = _string_default("streamlit_language")
DEFAULT_STREAMLIT_SAVE_FILE: Final = _path_default("streamlit_save_file")
DEFAULT_STREAMLIT_DEFAULT_SEED: Final = _integer_default("streamlit_default_seed")
DEFAULT_STREAMLIT_DEFAULT_HUMAN_PLAYER_ID: Final = _string_default(
    "streamlit_default_human_player_id"
)
DEFAULT_STREAMLIT_MESSAGE_MAX_CHARS: Final = _integer_default("streamlit_message_max_chars")
DEFAULT_STREAMLIT_PAGE_TITLE: Final = _string_default("streamlit_page_title")
DEFAULT_STREAMLIT_SERVICE_NAME: Final = _string_default("streamlit_service_name")
DEFAULT_API_TITLE: Final = _string_default("api_title")
DEFAULT_API_VERSION: Final = _string_default("api_version")
DEFAULT_API_DEBUG: Final = _bool_default("api_debug")
DEFAULT_API_CORS_ALLOWED_ORIGINS: Final = _string_default("api_cors_allowed_origins")
DEFAULT_API_CORS_ALLOWED_METHODS: Final = _string_default("api_cors_allowed_methods")
DEFAULT_API_CORS_ALLOWED_HEADERS: Final = _string_default("api_cors_allowed_headers")
DEFAULT_GAME_MIN_PLAYERS: Final = _integer_default("game_min_players")
DEFAULT_GAME_MAX_PLAYERS: Final = _integer_default("game_max_players")
DEFAULT_GAME_DEFAULT_PLAYER_COUNT: Final = _integer_default("game_default_player_count")
DEFAULT_GAME_SUPPORTED_AGENT_TYPE: Final = _string_default("game_supported_agent_type")
DEFAULT_GAME_SUPPORTED_AGENT_NAME: Final = _string_default("game_supported_agent_name")
DEFAULT_GAME_DEFAULT_RULESET_ID: Final = _string_default("game_default_ruleset_id")
DEFAULT_GAME_DEFAULT_RULESET_NAME: Final = _string_default("game_default_ruleset_name")
DEFAULT_GAME_DEFAULT_TIE_BREAK_POLICY: Final = _string_default("game_default_tie_break_policy")
DEFAULT_GAME_DEFAULT_DAY_SPEECH_TURNS: Final = _integer_default("game_default_day_speech_turns")
DEFAULT_GAME_DEFAULT_ALLOW_SELF_VOTE: Final = _bool_default("game_default_allow_self_vote")
DEFAULT_GAME_RULESET_DESCRIPTION_TEMPLATE: Final = _string_default(
    "game_ruleset_description_template"
)
DEFAULT_GAME_ROLE_NAMES: Final = _string_default("game_role_names")
DEFAULT_GAME_PHASE_NAMES: Final = _string_default("game_phase_names")

LOG_LEVEL_NAMES: Final = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
LOG_OUTPUT_NAMES: Final = frozenset({"file", "stderr", "stdout", "both", "none"})
CLI_OUTPUT_FORMAT_NAMES: Final = frozenset({"table", "json", "jsonl"})
STREAMLIT_LANGUAGE_NAMES: Final = frozenset({"ja", "en"})
LLM_PROVIDER_NAMES: Final = frozenset({DEFAULT_LLM_PROVIDER})
TIE_BREAK_POLICY_NAMES: Final = frozenset({"no_elimination", "random_elimination"})
SUPPORTED_AGENT_TYPE_NAMES: Final = frozenset({DEFAULT_GAME_SUPPORTED_AGENT_TYPE})

LogOutput = Literal["file", "stderr", "stdout", "both", "none"]
CliOutputFormat = Literal["table", "json", "jsonl"]
StreamlitLanguage = Literal["ja", "en"]
TieBreakPolicyName = Literal["no_elimination", "random_elimination"]


@lru_cache(maxsize=1)
def repository_root() -> Path:
    """Return the repository root when running from a source checkout."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def _optional_repository_path(value: str) -> Path | None:
    path_text = value.strip()
    if not path_text:
        return None
    path = Path(path_text).expanduser()
    if path.is_absolute():
        return path
    return repository_root() / path


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
    llm_prompt_file: str = Field(
        default=DEFAULT_LLM_PROMPT_FILE,
        validation_alias="WEREWOLF_LLM_PROMPT_FILE",
    )
    llm_fake_responses_file: str = Field(
        default=DEFAULT_LLM_FAKE_RESPONSES_FILE,
        validation_alias="WEREWOLF_LLM_FAKE_RESPONSES_FILE",
    )
    log_level: str = Field(default=DEFAULT_LOG_LEVEL, validation_alias="WEREWOLF_LOG_LEVEL")
    log_output: LogOutput = Field(
        default=cast(LogOutput, DEFAULT_LOG_OUTPUT),
        validation_alias="WEREWOLF_LOG_OUTPUT",
    )
    log_dir: Path = Field(default=DEFAULT_LOG_DIR, validation_alias="WEREWOLF_LOG_DIR")
    log_file_name: str = Field(
        default=DEFAULT_LOG_FILE_NAME,
        validation_alias="WEREWOLF_LOG_FILE_NAME",
    )
    log_retention_days: int = Field(
        default=DEFAULT_LOG_RETENTION_DAYS,
        ge=0,
        validation_alias="WEREWOLF_LOG_RETENTION_DAYS",
    )
    log_third_party_level: str = Field(
        default=DEFAULT_LOG_THIRD_PARTY_LEVEL,
        validation_alias="WEREWOLF_LOG_THIRD_PARTY_LEVEL",
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
        default=cast(CliOutputFormat, DEFAULT_CLI_OUTPUT_FORMAT),
        validation_alias="WEREWOLF_CLI_OUTPUT_FORMAT",
    )
    streamlit_api_url: str = Field(
        default=DEFAULT_STREAMLIT_API_URL,
        validation_alias="WEREWOLF_STREAMLIT_API_URL",
    )
    streamlit_http_timeout_seconds: float = Field(
        default=DEFAULT_STREAMLIT_HTTP_TIMEOUT_SECONDS,
        gt=0,
        validation_alias="WEREWOLF_STREAMLIT_HTTP_TIMEOUT_SECONDS",
    )
    streamlit_refresh_interval_seconds: float = Field(
        default=DEFAULT_STREAMLIT_REFRESH_INTERVAL_SECONDS,
        ge=0,
        validation_alias="WEREWOLF_STREAMLIT_REFRESH_INTERVAL_SECONDS",
    )
    streamlit_event_limit: int = Field(
        default=DEFAULT_STREAMLIT_EVENT_LIMIT,
        ge=1,
        le=500,
        validation_alias="WEREWOLF_STREAMLIT_EVENT_LIMIT",
    )
    streamlit_turn_limit: int = Field(
        default=DEFAULT_STREAMLIT_TURN_LIMIT,
        ge=1,
        le=500,
        validation_alias="WEREWOLF_STREAMLIT_TURN_LIMIT",
    )
    streamlit_run_limit: int = Field(
        default=DEFAULT_STREAMLIT_RUN_LIMIT,
        ge=1,
        le=100,
        validation_alias="WEREWOLF_STREAMLIT_RUN_LIMIT",
    )
    streamlit_max_auto_steps: int = Field(
        default=DEFAULT_STREAMLIT_MAX_AUTO_STEPS,
        ge=1,
        validation_alias="WEREWOLF_STREAMLIT_MAX_AUTO_STEPS",
    )
    streamlit_language: StreamlitLanguage = Field(
        default=cast(StreamlitLanguage, DEFAULT_STREAMLIT_LANGUAGE),
        validation_alias="WEREWOLF_STREAMLIT_LANGUAGE",
    )
    streamlit_save_file: Path = Field(
        default=DEFAULT_STREAMLIT_SAVE_FILE,
        validation_alias="WEREWOLF_STREAMLIT_SAVE_FILE",
    )
    streamlit_page_title: str = Field(
        default=DEFAULT_STREAMLIT_PAGE_TITLE,
        validation_alias="WEREWOLF_STREAMLIT_PAGE_TITLE",
    )
    streamlit_default_seed: int = Field(
        default=DEFAULT_STREAMLIT_DEFAULT_SEED,
        validation_alias="WEREWOLF_STREAMLIT_DEFAULT_SEED",
    )
    streamlit_default_human_player_id: str = Field(
        default=DEFAULT_STREAMLIT_DEFAULT_HUMAN_PLAYER_ID,
        validation_alias="WEREWOLF_STREAMLIT_DEFAULT_HUMAN_PLAYER_ID",
    )
    streamlit_message_max_chars: int = Field(
        default=DEFAULT_STREAMLIT_MESSAGE_MAX_CHARS,
        ge=1,
        validation_alias="WEREWOLF_STREAMLIT_MESSAGE_MAX_CHARS",
    )
    streamlit_service_name: str = Field(
        default=DEFAULT_STREAMLIT_SERVICE_NAME,
        validation_alias="WEREWOLF_STREAMLIT_SERVICE_NAME",
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
    game_default_tie_break_policy: TieBreakPolicyName = Field(
        default=cast(TieBreakPolicyName, DEFAULT_GAME_DEFAULT_TIE_BREAK_POLICY),
        validation_alias="WEREWOLF_GAME_DEFAULT_TIE_BREAK_POLICY",
    )
    game_default_day_speech_turns: int = Field(
        default=DEFAULT_GAME_DEFAULT_DAY_SPEECH_TURNS,
        ge=1,
        le=5,
        validation_alias="WEREWOLF_GAME_DEFAULT_DAY_SPEECH_TURNS",
    )
    game_default_allow_self_vote: bool = Field(
        default=DEFAULT_GAME_DEFAULT_ALLOW_SELF_VOTE,
        validation_alias="WEREWOLF_GAME_DEFAULT_ALLOW_SELF_VOTE",
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
    api_service_name: str = Field(
        default=DEFAULT_API_SERVICE_NAME,
        validation_alias="WEREWOLF_API_SERVICE_NAME",
    )
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
    def streamlit_resolved_api_url(self) -> str:
        """Return Streamlit API URL, falling back to the CLI API URL."""
        api_url = self.streamlit_api_url.strip()
        return api_url or self.cli_api_url

    @property
    def streamlit_save_file_path(self) -> Path:
        """Return the absolute local save-slot file for the Streamlit UI."""
        save_file = self.streamlit_save_file.expanduser()
        if save_file.is_absolute():
            return save_file
        return repository_root() / save_file

    @property
    def sqlite_database_path(self) -> Path:
        """Return an absolute SQLite path, creating parent directories on demand elsewhere."""
        sqlite_path = self.sqlite_path.expanduser()
        if sqlite_path.is_absolute():
            return sqlite_path
        return repository_root() / sqlite_path

    @property
    def llm_prompt_path(self) -> Path | None:
        """Return the configured external LLM prompt file, if any."""
        return _optional_repository_path(self.llm_prompt_file)

    @property
    def llm_fake_responses_path(self) -> Path | None:
        """Return the configured external FakeListLLM response file, if any."""
        return _optional_repository_path(self.llm_fake_responses_file)

    @property
    def log_directory_path(self) -> Path:
        """Return the absolute directory for operational logs."""
        log_dir = self.log_dir.expanduser()
        if log_dir.is_absolute():
            return log_dir
        return repository_root() / log_dir

    @property
    def log_file_path(self) -> Path:
        """Return the active operational JSONL log file path."""
        return self.log_directory_path / self.log_file_name

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

    @field_validator("log_output", mode="before")
    @classmethod
    def normalize_log_output(cls, value: object) -> str:
        """Return a validated lowercase logging output target."""
        return normalize_choice(
            value,
            field_name="log_output",
            choices=LOG_OUTPUT_NAMES,
            case="lower",
        )

    @field_validator("log_third_party_level", mode="before")
    @classmethod
    def normalize_log_third_party_level(cls, value: object) -> str:
        """Return a validated uppercase logging level for third-party libraries."""
        return normalize_choice(
            value,
            field_name="log_third_party_level",
            choices=LOG_LEVEL_NAMES,
            case="upper",
        )

    @field_validator("log_file_name", mode="before")
    @classmethod
    def normalize_log_file_name(cls, value: object) -> str:
        """Return a safe non-empty operational log file name."""
        file_name = normalize_non_blank(value, field_name="log_file_name")
        if Path(file_name).name != file_name:
            raise ValueError("log_file_name must be a file name")
        return file_name

    @field_validator("streamlit_language", mode="before")
    @classmethod
    def normalize_streamlit_language(cls, value: object) -> str:
        """Return a validated Streamlit UI language."""
        return normalize_choice(
            value,
            field_name="streamlit_language",
            choices=STREAMLIT_LANGUAGE_NAMES,
            case="lower",
        )

    @field_validator("streamlit_page_title", "streamlit_service_name", mode="before")
    @classmethod
    def normalize_streamlit_text(cls, value: object, info: ValidationInfo) -> str:
        """Return non-empty Streamlit display/service settings."""
        return normalize_non_blank(value, field_name=str(info.field_name))

    @field_validator("streamlit_default_human_player_id", mode="before")
    @classmethod
    def normalize_streamlit_player_id(cls, value: object) -> str:
        """Return the default Streamlit player id."""
        return normalize_non_blank(value, field_name="streamlit_default_human_player_id")

    @field_validator("streamlit_save_file", mode="before")
    @classmethod
    def normalize_streamlit_save_file(cls, value: object) -> Path:
        """Return a non-empty Streamlit save file path."""
        if isinstance(value, Path):
            return value
        return Path(normalize_non_blank(value, field_name="streamlit_save_file"))

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

    @field_validator("game_default_tie_break_policy", mode="before")
    @classmethod
    def normalize_game_default_tie_break_policy(cls, value: object) -> str:
        """Return a validated default tie-break policy."""
        return normalize_choice(
            value,
            field_name="game_default_tie_break_policy",
            choices=TIE_BREAK_POLICY_NAMES,
            case="lower",
        )

    @field_validator(
        "game_supported_agent_name",
        "game_default_ruleset_id",
        "game_default_ruleset_name",
        "game_ruleset_description_template",
        "game_role_names",
        "game_phase_names",
        "api_title",
        "api_service_name",
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
