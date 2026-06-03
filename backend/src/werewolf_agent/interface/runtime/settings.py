"""Environment-backed settings for user-facing interfaces."""

from __future__ import annotations

import os
from collections.abc import Mapping
from functools import cached_property, lru_cache
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

from werewolf_agent.commons.shared.constants import (
    CLI_OUTPUT_FORMAT_CHOICE_SET,
    LLM_PROVIDER_CHOICE_SET,
    LLM_PROVIDER_LMSTUDIO,
    LLM_PROVIDER_OPENAI,
    LOG_OUTPUT_CHOICE_SET,
    MAX_GAME_LIST_LIMIT,
    MAX_LLM_TEMPERATURE,
    MAX_TIMELINE_LIMIT,
    MIN_INTERVAL_SECONDS,
    MIN_INTERVAL_SECONDS_EXCLUSIVE,
    MIN_LLM_TEMPERATURE,
    MIN_PAGE_LIMIT,
    MIN_PLAYER_COUNT,
    MIN_RETENTION_DAYS,
    MIN_RETRY_COUNT,
    MIN_STEP_LIMIT,
    MIN_TEXT_MAX_CHARS,
    MIN_TIMEOUT_SECONDS_EXCLUSIVE,
    NARRATION_MODE_CHOICES,
)
from werewolf_agent.commons.shared.constants import (
    CliOutputFormat as SharedCliOutputFormat,
)
from werewolf_agent.commons.shared.constants import (
    LogOutput as SharedLogOutput,
)
from werewolf_agent.commons.shared.constants import (
    NarrationMode as SharedNarrationMode,
)
from werewolf_agent.commons.shared.definitions import GameDefinitions, LlmDefinitions
from werewolf_agent.commons.shared.messages import (
    MESSAGE_LOG_FILE_NAME_MUST_BE_FILE_NAME,
    MESSAGE_SUPABASE_CLIENT_SETTINGS_MUST_BE_PAIRED,
    MESSAGE_SUPABASE_URL_MUST_START_WITH_HTTP,
    message_definition_settings_invalid,
    message_field_must_be_le_field,
    message_game_default_player_count_between,
    message_game_min_players_le_max_players,
    message_game_setup_description_template_invalid,
    message_mapping_item_must_use_separator,
    message_missing_default_setting,
    message_role_definition_missing_player_counts,
    message_settings_llm_base_url_required,
    message_settings_openai_api_key_required,
)
from werewolf_agent.commons.shared.validation import normalize_choice, normalize_non_blank
from werewolf_agent.interface.runtime.resources import (
    load_game_definitions,
    load_llm_definitions,
    load_packaged_defaults,
)

PACKAGED_DEFAULTS: Mapping[str, object] = load_packaged_defaults()


def _default_value(key: str) -> object:
    try:
        return PACKAGED_DEFAULTS[key]
    except KeyError as exc:
        raise RuntimeError(message_missing_default_setting(key)) from exc


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
DEFAULT_LLM_PROVIDER: Final = _string_default("llm_provider")
DEFAULT_LLM_MODEL: Final = _string_default("model")
DEFAULT_LLM_BASE_URL: Final = _string_default("llm_base_url")
DEFAULT_LLM_TIMEOUT_SECONDS: Final = _float_default("llm_timeout_seconds")
DEFAULT_LLM_MAX_RETRIES: Final = _integer_default("llm_max_retries")
DEFAULT_LLM_MAX_TOKENS: Final = _integer_default("llm_max_tokens")
DEFAULT_LLM_TEMPERATURE: Final = _float_default("llm_temperature")
DEFAULT_LLM_PROMPT_FILE: Final = _string_default("llm_prompt_file")
DEFAULT_LLM_FAKE_RESPONSES_FILE: Final = _string_default("llm_fake_responses_file")
DEFAULT_LLM_PLAYERS_FILE: Final = _string_default("llm_players_file")
DEFAULT_LOG_LEVEL: Final = _string_default("log_level")
DEFAULT_LOG_OUTPUT: Final = _string_default("log_output")
DEFAULT_LOG_DIR: Final = _path_default("log_dir")
DEFAULT_LOG_FILE_NAME: Final = _string_default("log_file_name")
DEFAULT_LOG_RETENTION_DAYS: Final = _integer_default("log_retention_days")
DEFAULT_LOG_THIRD_PARTY_LEVEL: Final = _string_default("log_third_party_level")
DEFAULT_SUPABASE_URL: Final = _string_default("supabase_url")
DEFAULT_SUPABASE_PUBLISHABLE_KEY: Final = _string_default("supabase_publishable_key")
DEFAULT_SUPABASE_DB_DSN: Final = _string_default("supabase_db_dsn")
DEFAULT_SUPABASE_AUTH_TIMEOUT_SECONDS: Final = _float_default("supabase_auth_timeout_seconds")
DEFAULT_SUPABASE_REST_TIMEOUT_SECONDS: Final = _float_default("supabase_rest_timeout_seconds")
DEFAULT_SUPABASE_WORKER_ID: Final = _string_default("supabase_worker_id")
DEFAULT_SUPABASE_WORKER_POLL_INTERVAL_SECONDS: Final = _float_default(
    "supabase_worker_poll_interval_seconds"
)
DEFAULT_SUPABASE_WORKER_BATCH_SIZE: Final = _integer_default("supabase_worker_batch_size")
DEFAULT_SUPABASE_WORKER_CLAIM_SECONDS: Final = _integer_default("supabase_worker_claim_seconds")
DEFAULT_LLM_TRACE_RETENTION_DAYS: Final = _integer_default("llm_trace_retention_days")
DEFAULT_ADVANCE_JOB_POLL_INTERVAL_SECONDS: Final = _float_default(
    "advance_job_poll_interval_seconds"
)
DEFAULT_ADVANCE_JOB_POLL_TIMEOUT_SECONDS: Final = _float_default("advance_job_poll_timeout_seconds")
DEFAULT_CLI_MAX_STEPS: Final = _integer_default("cli_max_steps")
DEFAULT_CLI_POLL_INTERVAL_SECONDS: Final = _float_default("cli_poll_interval_seconds")
DEFAULT_CLI_EVENT_LIMIT: Final = _integer_default("cli_event_limit")
DEFAULT_CLI_OUTPUT_FORMAT: Final = _string_default("cli_output_format")
DEFAULT_STREAMLIT_REFRESH_INTERVAL_SECONDS: Final = _float_default(
    "streamlit_refresh_interval_seconds"
)
DEFAULT_STREAMLIT_TURN_LIMIT: Final = _integer_default("streamlit_turn_limit")
DEFAULT_STREAMLIT_RUN_LIMIT: Final = _integer_default("streamlit_run_limit")
DEFAULT_STREAMLIT_MAX_AUTO_STEPS: Final = _integer_default("streamlit_max_auto_steps")
DEFAULT_STREAMLIT_AUTO_ADVANCE_INTERVAL_SECONDS: Final = _float_default(
    "streamlit_auto_advance_interval_seconds"
)
DEFAULT_STREAMLIT_INITIAL_SIDEBAR_STATE: Final = _string_default("streamlit_initial_sidebar_state")
DEFAULT_STREAMLIT_LANGUAGE: Final = _string_default("streamlit_language")
DEFAULT_STREAMLIT_I18N_FILE: Final = _string_default("streamlit_i18n_file")
DEFAULT_STREAMLIT_CSS_FILE: Final = _string_default("streamlit_css_file")
DEFAULT_STREAMLIT_SCREENS_FILE: Final = _string_default("streamlit_screens_file")
DEFAULT_STREAMLIT_DEFAULT_SEED: Final = _integer_default("streamlit_default_seed")
DEFAULT_STREAMLIT_RANDOM_SEED_MAX: Final = _integer_default("streamlit_random_seed_max")
DEFAULT_STREAMLIT_DEFAULT_MANUAL_PLAYER_ID: Final = _string_default(
    "streamlit_default_manual_player_id"
)
DEFAULT_STREAMLIT_MESSAGE_MAX_CHARS: Final = _integer_default("streamlit_message_max_chars")
DEFAULT_STREAMLIT_PAGE_TITLE: Final = _string_default("streamlit_page_title")
DEFAULT_STREAMLIT_SERVICE_NAME: Final = _string_default("streamlit_service_name")
DEFAULT_API_TITLE: Final = _string_default("api_title")
DEFAULT_API_VERSION: Final = _string_default("api_version")
DEFAULT_API_DEBUG: Final = _bool_default("api_debug")
DEFAULT_REVEAL_API_ENABLED: Final = _bool_default("reveal_api_enabled")
DEFAULT_API_GAME_LIST_DEFAULT_LIMIT: Final = _integer_default("api_game_list_default_limit")
DEFAULT_API_GAME_LIST_MAX_LIMIT: Final = _integer_default("api_game_list_max_limit")
DEFAULT_API_TIMELINE_DEFAULT_LIMIT: Final = _integer_default("api_timeline_default_limit")
DEFAULT_API_TIMELINE_MAX_LIMIT: Final = _integer_default("api_timeline_max_limit")
DEFAULT_API_CORS_ALLOWED_ORIGINS: Final = _string_default("api_cors_allowed_origins")
DEFAULT_API_CORS_ALLOWED_METHODS: Final = _string_default("api_cors_allowed_methods")
DEFAULT_API_CORS_ALLOWED_HEADERS: Final = _string_default("api_cors_allowed_headers")
DEFAULT_GAME_MIN_PLAYERS: Final = _integer_default("game_min_players")
DEFAULT_GAME_MAX_PLAYERS: Final = _integer_default("game_max_players")
DEFAULT_GAME_DEFAULT_PLAYER_COUNT: Final = _integer_default("game_default_player_count")
DEFAULT_GAME_SUPPORTED_AGENT_TYPE: Final = _string_default("game_supported_agent_type")
DEFAULT_GAME_SUPPORTED_AGENT_NAME: Final = _string_default("game_supported_agent_name")
DEFAULT_GAME_DEFAULT_NARRATION_MODE: Final = _string_default("game_default_narration_mode")
DEFAULT_GAME_DEFAULT_SETUP_ID: Final = _string_default("game_default_setup_id")
DEFAULT_GAME_DEFAULT_SETUP_NAME: Final = _string_default("game_default_setup_name")
DEFAULT_GAME_RULES_FILE: Final = _string_default("game_rules_file")
DEFAULT_GAME_ROLES_FILE: Final = _string_default("game_roles_file")
DEFAULT_GAME_CATALOG_FILE: Final = _string_default("game_catalog_file")
DEFAULT_GAME_SETUP_DESCRIPTION_TEMPLATE: Final = _string_default("game_setup_description_template")
DEFAULT_GAME_ROLE_NAMES: Final = _string_default("game_role_names")
DEFAULT_GAME_PHASE_NAMES: Final = _string_default("game_phase_names")

LOG_LEVEL_NAMES: Final = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
LOG_OUTPUT_NAMES: Final = LOG_OUTPUT_CHOICE_SET
CLI_OUTPUT_FORMAT_NAMES: Final = CLI_OUTPUT_FORMAT_CHOICE_SET
STREAMLIT_LANGUAGE_NAMES: Final = frozenset({"ja", "en"})
STREAMLIT_SIDEBAR_STATE_NAMES: Final = frozenset({"auto", "expanded", "collapsed"})
LLM_PROVIDER_NAMES: Final = LLM_PROVIDER_CHOICE_SET
SUPPORTED_AGENT_TYPE_NAMES: Final = frozenset({DEFAULT_GAME_SUPPORTED_AGENT_TYPE})

StreamlitLanguage = Literal["ja", "en"]
StreamlitSidebarState = Literal["auto", "expanded", "collapsed"]


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
    llm_base_url: str = Field(
        default=DEFAULT_LLM_BASE_URL,
        validation_alias="WEREWOLF_LLM_BASE_URL",
    )
    llm_timeout_seconds: float = Field(
        default=DEFAULT_LLM_TIMEOUT_SECONDS,
        gt=MIN_TIMEOUT_SECONDS_EXCLUSIVE,
        validation_alias="WEREWOLF_LLM_TIMEOUT_SECONDS",
    )
    llm_max_retries: int = Field(
        default=DEFAULT_LLM_MAX_RETRIES,
        ge=MIN_RETRY_COUNT,
        validation_alias="WEREWOLF_LLM_MAX_RETRIES",
    )
    llm_max_tokens: int = Field(
        default=DEFAULT_LLM_MAX_TOKENS,
        ge=1,
        validation_alias="WEREWOLF_LLM_MAX_TOKENS",
    )
    llm_temperature: float = Field(
        default=DEFAULT_LLM_TEMPERATURE,
        ge=MIN_LLM_TEMPERATURE,
        le=MAX_LLM_TEMPERATURE,
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
    llm_players_file: str = Field(
        default=DEFAULT_LLM_PLAYERS_FILE,
        validation_alias="WEREWOLF_LLM_PLAYERS_FILE",
    )
    log_level: str = Field(default=DEFAULT_LOG_LEVEL, validation_alias="WEREWOLF_LOG_LEVEL")
    log_output: SharedLogOutput = Field(
        default=cast(SharedLogOutput, DEFAULT_LOG_OUTPUT),
        validation_alias="WEREWOLF_LOG_OUTPUT",
    )
    log_dir: Path = Field(default=DEFAULT_LOG_DIR, validation_alias="WEREWOLF_LOG_DIR")
    log_file_name: str = Field(
        default=DEFAULT_LOG_FILE_NAME,
        validation_alias="WEREWOLF_LOG_FILE_NAME",
    )
    log_retention_days: int = Field(
        default=DEFAULT_LOG_RETENTION_DAYS,
        ge=MIN_RETENTION_DAYS,
        validation_alias="WEREWOLF_LOG_RETENTION_DAYS",
    )
    log_third_party_level: str = Field(
        default=DEFAULT_LOG_THIRD_PARTY_LEVEL,
        validation_alias="WEREWOLF_LOG_THIRD_PARTY_LEVEL",
    )
    supabase_url: str = Field(
        default=DEFAULT_SUPABASE_URL,
        validation_alias="WEREWOLF_SUPABASE_URL",
    )
    supabase_publishable_key: SecretStr = Field(
        default=SecretStr(DEFAULT_SUPABASE_PUBLISHABLE_KEY),
        validation_alias="WEREWOLF_SUPABASE_PUBLISHABLE_KEY",
    )
    supabase_db_dsn: SecretStr = Field(
        default=SecretStr(DEFAULT_SUPABASE_DB_DSN),
        validation_alias=AliasChoices("WEREWOLF_SUPABASE_DB_DSN", "SUPABASE_DB_DSN"),
    )
    supabase_auth_timeout_seconds: float = Field(
        default=DEFAULT_SUPABASE_AUTH_TIMEOUT_SECONDS,
        gt=MIN_TIMEOUT_SECONDS_EXCLUSIVE,
        validation_alias="WEREWOLF_SUPABASE_AUTH_TIMEOUT_SECONDS",
    )
    supabase_rest_timeout_seconds: float = Field(
        default=DEFAULT_SUPABASE_REST_TIMEOUT_SECONDS,
        gt=MIN_TIMEOUT_SECONDS_EXCLUSIVE,
        validation_alias="WEREWOLF_SUPABASE_REST_TIMEOUT_SECONDS",
    )
    supabase_worker_id: str = Field(
        default=DEFAULT_SUPABASE_WORKER_ID,
        validation_alias="WEREWOLF_SUPABASE_WORKER_ID",
    )
    supabase_worker_poll_interval_seconds: float = Field(
        default=DEFAULT_SUPABASE_WORKER_POLL_INTERVAL_SECONDS,
        ge=MIN_INTERVAL_SECONDS,
        validation_alias="WEREWOLF_SUPABASE_WORKER_POLL_INTERVAL_SECONDS",
    )
    supabase_worker_batch_size: int = Field(
        default=DEFAULT_SUPABASE_WORKER_BATCH_SIZE,
        ge=1,
        validation_alias="WEREWOLF_SUPABASE_WORKER_BATCH_SIZE",
    )
    supabase_worker_claim_seconds: int = Field(
        default=DEFAULT_SUPABASE_WORKER_CLAIM_SECONDS,
        ge=1,
        validation_alias="WEREWOLF_SUPABASE_WORKER_CLAIM_SECONDS",
    )
    llm_trace_retention_days: int = Field(
        default=DEFAULT_LLM_TRACE_RETENTION_DAYS,
        ge=MIN_RETENTION_DAYS,
        validation_alias="WEREWOLF_LLM_TRACE_RETENTION_DAYS",
    )
    advance_job_poll_interval_seconds: float = Field(
        default=DEFAULT_ADVANCE_JOB_POLL_INTERVAL_SECONDS,
        ge=MIN_INTERVAL_SECONDS,
        validation_alias="WEREWOLF_ADVANCE_JOB_POLL_INTERVAL_SECONDS",
    )
    advance_job_poll_timeout_seconds: float = Field(
        default=DEFAULT_ADVANCE_JOB_POLL_TIMEOUT_SECONDS,
        gt=MIN_TIMEOUT_SECONDS_EXCLUSIVE,
        validation_alias="WEREWOLF_ADVANCE_JOB_POLL_TIMEOUT_SECONDS",
    )
    cli_max_steps: int = Field(
        default=DEFAULT_CLI_MAX_STEPS,
        ge=MIN_STEP_LIMIT,
        validation_alias="WEREWOLF_CLI_MAX_STEPS",
    )
    cli_poll_interval_seconds: float = Field(
        default=DEFAULT_CLI_POLL_INTERVAL_SECONDS,
        ge=MIN_INTERVAL_SECONDS,
        validation_alias="WEREWOLF_CLI_POLL_INTERVAL_SECONDS",
    )
    cli_event_limit: int = Field(
        default=DEFAULT_CLI_EVENT_LIMIT,
        ge=MIN_PAGE_LIMIT,
        le=MAX_TIMELINE_LIMIT,
        validation_alias="WEREWOLF_CLI_EVENT_LIMIT",
    )
    cli_output_format: SharedCliOutputFormat = Field(
        default=cast(SharedCliOutputFormat, DEFAULT_CLI_OUTPUT_FORMAT),
        validation_alias="WEREWOLF_CLI_OUTPUT_FORMAT",
    )
    streamlit_refresh_interval_seconds: float = Field(
        default=DEFAULT_STREAMLIT_REFRESH_INTERVAL_SECONDS,
        ge=MIN_INTERVAL_SECONDS,
        validation_alias="WEREWOLF_STREAMLIT_REFRESH_INTERVAL_SECONDS",
    )
    streamlit_turn_limit: int = Field(
        default=DEFAULT_STREAMLIT_TURN_LIMIT,
        ge=MIN_PAGE_LIMIT,
        le=MAX_TIMELINE_LIMIT,
        validation_alias="WEREWOLF_STREAMLIT_TURN_LIMIT",
    )
    streamlit_run_limit: int = Field(
        default=DEFAULT_STREAMLIT_RUN_LIMIT,
        ge=MIN_PAGE_LIMIT,
        le=MAX_GAME_LIST_LIMIT,
        validation_alias="WEREWOLF_STREAMLIT_RUN_LIMIT",
    )
    streamlit_max_auto_steps: int = Field(
        default=DEFAULT_STREAMLIT_MAX_AUTO_STEPS,
        ge=MIN_STEP_LIMIT,
        validation_alias="WEREWOLF_STREAMLIT_MAX_AUTO_STEPS",
    )
    streamlit_auto_advance_interval_seconds: float = Field(
        default=DEFAULT_STREAMLIT_AUTO_ADVANCE_INTERVAL_SECONDS,
        gt=MIN_INTERVAL_SECONDS_EXCLUSIVE,
        validation_alias="WEREWOLF_STREAMLIT_AUTO_ADVANCE_INTERVAL_SECONDS",
    )
    streamlit_initial_sidebar_state: StreamlitSidebarState = Field(
        default=cast(StreamlitSidebarState, DEFAULT_STREAMLIT_INITIAL_SIDEBAR_STATE),
        validation_alias="WEREWOLF_STREAMLIT_INITIAL_SIDEBAR_STATE",
    )
    streamlit_language: StreamlitLanguage = Field(
        default=cast(StreamlitLanguage, DEFAULT_STREAMLIT_LANGUAGE),
        validation_alias="WEREWOLF_STREAMLIT_LANGUAGE",
    )
    streamlit_i18n_file: str = Field(
        default=DEFAULT_STREAMLIT_I18N_FILE,
        validation_alias="WEREWOLF_STREAMLIT_I18N_FILE",
    )
    streamlit_css_file: str = Field(
        default=DEFAULT_STREAMLIT_CSS_FILE,
        validation_alias="WEREWOLF_STREAMLIT_CSS_FILE",
    )
    streamlit_screens_file: str = Field(
        default=DEFAULT_STREAMLIT_SCREENS_FILE,
        validation_alias="WEREWOLF_STREAMLIT_SCREENS_FILE",
    )
    streamlit_page_title: str = Field(
        default=DEFAULT_STREAMLIT_PAGE_TITLE,
        validation_alias="WEREWOLF_STREAMLIT_PAGE_TITLE",
    )
    streamlit_default_seed: int = Field(
        default=DEFAULT_STREAMLIT_DEFAULT_SEED,
        validation_alias="WEREWOLF_STREAMLIT_DEFAULT_SEED",
    )
    streamlit_random_seed_max: int = Field(
        default=DEFAULT_STREAMLIT_RANDOM_SEED_MAX,
        ge=1,
        validation_alias="WEREWOLF_STREAMLIT_RANDOM_SEED_MAX",
    )
    streamlit_default_manual_player_id: str = Field(
        default=DEFAULT_STREAMLIT_DEFAULT_MANUAL_PLAYER_ID,
        validation_alias="WEREWOLF_STREAMLIT_DEFAULT_MANUAL_PLAYER_ID",
    )
    streamlit_message_max_chars: int = Field(
        default=DEFAULT_STREAMLIT_MESSAGE_MAX_CHARS,
        ge=MIN_TEXT_MAX_CHARS,
        validation_alias="WEREWOLF_STREAMLIT_MESSAGE_MAX_CHARS",
    )
    streamlit_service_name: str = Field(
        default=DEFAULT_STREAMLIT_SERVICE_NAME,
        validation_alias="WEREWOLF_STREAMLIT_SERVICE_NAME",
    )

    game_min_players: int = Field(
        default=DEFAULT_GAME_MIN_PLAYERS,
        ge=MIN_PLAYER_COUNT,
        validation_alias="WEREWOLF_GAME_MIN_PLAYERS",
    )
    game_max_players: int = Field(
        default=DEFAULT_GAME_MAX_PLAYERS,
        ge=MIN_PLAYER_COUNT,
        validation_alias="WEREWOLF_GAME_MAX_PLAYERS",
    )
    game_default_player_count: int = Field(
        default=DEFAULT_GAME_DEFAULT_PLAYER_COUNT,
        ge=MIN_PLAYER_COUNT,
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
    game_default_narration_mode: SharedNarrationMode = Field(
        default=cast(SharedNarrationMode, DEFAULT_GAME_DEFAULT_NARRATION_MODE),
        validation_alias="WEREWOLF_GAME_DEFAULT_NARRATION_MODE",
    )
    game_default_setup_id: str = Field(
        default=DEFAULT_GAME_DEFAULT_SETUP_ID,
        validation_alias="WEREWOLF_GAME_DEFAULT_SETUP_ID",
    )
    game_default_setup_name: str = Field(
        default=DEFAULT_GAME_DEFAULT_SETUP_NAME,
        validation_alias="WEREWOLF_GAME_DEFAULT_SETUP_NAME",
    )
    game_rules_file: str = Field(
        default=DEFAULT_GAME_RULES_FILE,
        validation_alias="WEREWOLF_GAME_RULES_FILE",
    )
    game_roles_file: str = Field(
        default=DEFAULT_GAME_ROLES_FILE,
        validation_alias="WEREWOLF_GAME_ROLES_FILE",
    )
    game_catalog_file: str = Field(
        default=DEFAULT_GAME_CATALOG_FILE,
        validation_alias="WEREWOLF_GAME_CATALOG_FILE",
    )
    game_setup_description_template: str = Field(
        default=DEFAULT_GAME_SETUP_DESCRIPTION_TEMPLATE,
        validation_alias="WEREWOLF_GAME_SETUP_DESCRIPTION_TEMPLATE",
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
    reveal_api_enabled: bool = Field(
        default=DEFAULT_REVEAL_API_ENABLED,
        validation_alias="WEREWOLF_REVEAL_API_ENABLED",
    )
    api_game_list_default_limit: int = Field(
        default=DEFAULT_API_GAME_LIST_DEFAULT_LIMIT,
        ge=MIN_PAGE_LIMIT,
        validation_alias="WEREWOLF_API_GAME_LIST_DEFAULT_LIMIT",
    )
    api_game_list_max_limit: int = Field(
        default=DEFAULT_API_GAME_LIST_MAX_LIMIT,
        ge=MIN_PAGE_LIMIT,
        validation_alias="WEREWOLF_API_GAME_LIST_MAX_LIMIT",
    )
    api_timeline_default_limit: int = Field(
        default=DEFAULT_API_TIMELINE_DEFAULT_LIMIT,
        ge=MIN_PAGE_LIMIT,
        validation_alias="WEREWOLF_API_TIMELINE_DEFAULT_LIMIT",
    )
    api_timeline_max_limit: int = Field(
        default=DEFAULT_API_TIMELINE_MAX_LIMIT,
        ge=MIN_PAGE_LIMIT,
        validation_alias="WEREWOLF_API_TIMELINE_MAX_LIMIT",
    )
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
    openai_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="OPENAI_API_KEY",
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
    def supabase_publishable_key_value(self) -> str:
        """Return the public Supabase browser/client key."""
        return self.supabase_publishable_key.get_secret_value().strip()

    @property
    def supabase_db_dsn_value(self) -> str:
        """Return the worker-only Supabase direct database DSN."""
        return self.supabase_db_dsn.get_secret_value().strip()

    @property
    def supabase_client_configured(self) -> bool:
        """Return whether UI/CLI can use Supabase directly."""
        return bool(self.supabase_url and self.supabase_publishable_key_value)

    @property
    def supabase_worker_configured(self) -> bool:
        """Return whether the worker can connect to Supabase Postgres."""
        return bool(self.supabase_db_dsn_value)

    @property
    def game_role_name_map(self) -> dict[str, str]:
        """Return configured public role display names."""
        return split_mapping(self.game_role_names, field_name="game_role_names")

    @property
    def game_phase_name_map(self) -> dict[str, str]:
        """Return configured public phase display names."""
        return split_mapping(self.game_phase_names, field_name="game_phase_names")

    @property
    def streamlit_i18n_path(self) -> Path | None:
        """Return the configured external Streamlit i18n file, if any."""
        return _optional_repository_path(self.streamlit_i18n_file)

    @property
    def streamlit_css_path(self) -> Path | None:
        """Return the configured external Streamlit CSS file, if any."""
        return _optional_repository_path(self.streamlit_css_file)

    @property
    def streamlit_screens_path(self) -> Path | None:
        """Return the configured external Streamlit screen definition file, if any."""
        return _optional_repository_path(self.streamlit_screens_file)

    @property
    def llm_prompt_path(self) -> Path | None:
        """Return the configured external LLM prompt file, if any."""
        return _optional_repository_path(self.llm_prompt_file)

    @property
    def llm_fake_responses_path(self) -> Path | None:
        """Return the configured external FakeListLLM response file, if any."""
        return _optional_repository_path(self.llm_fake_responses_file)

    @property
    def llm_players_path(self) -> Path | None:
        """Return the configured external LLM player definition file, if any."""
        return _optional_repository_path(self.llm_players_file)

    @property
    def game_rules_path(self) -> Path | None:
        """Return the configured external game rule definition file, if any."""
        return _optional_repository_path(self.game_rules_file)

    @property
    def game_roles_path(self) -> Path | None:
        """Return the configured external game role definition file, if any."""
        return _optional_repository_path(self.game_roles_file)

    @property
    def game_catalog_path(self) -> Path | None:
        """Return the configured external game catalog definition file, if any."""
        return _optional_repository_path(self.game_catalog_file)

    @cached_property
    def game_definitions(self) -> GameDefinitions:
        """Return game definitions loaded by runtime settings."""
        return load_game_definitions(
            rules_path=self.game_rules_path,
            roles_path=self.game_roles_path,
            catalog_path=self.game_catalog_path,
        )

    @cached_property
    def llm_definitions(self) -> LlmDefinitions:
        """Return LLM definitions loaded by runtime settings."""
        return load_llm_definitions(
            players_path=self.llm_players_path,
            prompt_path=self.llm_prompt_path,
            fake_responses_path=self.llm_fake_responses_path,
        )

    @property
    def log_directory_path(self) -> Path:
        """Return the absolute directory for operational logs."""
        log_dir_text = str(self.log_dir).strip()
        log_dir = Path(os.path.expandvars(log_dir_text)).expanduser()
        if log_dir.is_absolute():
            return log_dir
        return repository_root() / log_dir

    @property
    def log_file_path(self) -> Path:
        """Return the active operational JSONL log file path."""
        return self.log_directory_path / self.log_file_name

    @property
    def configured_openai_api_key(self) -> str:
        """Return the configured OpenAI-compatible API key without exposing it in repr output."""
        return self.openai_api_key.get_secret_value().strip()

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
            raise ValueError(MESSAGE_LOG_FILE_NAME_MUST_BE_FILE_NAME)
        return file_name

    @field_validator("supabase_url", mode="before")
    @classmethod
    def normalize_supabase_url(cls, value: object) -> str:
        """Return an optional Supabase project URL."""
        if value is None:
            return ""
        url = str(value).strip().rstrip("/")
        if not url:
            return ""
        if not url.startswith(("http://", "https://")):
            raise ValueError(MESSAGE_SUPABASE_URL_MUST_START_WITH_HTTP)
        return url

    @field_validator("supabase_worker_id", mode="before")
    @classmethod
    def normalize_supabase_worker_id(cls, value: object) -> str:
        """Return a non-empty worker id for queue ownership."""
        return normalize_non_blank(value, field_name="supabase_worker_id")

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

    @field_validator("streamlit_initial_sidebar_state", mode="before")
    @classmethod
    def normalize_streamlit_sidebar_state(cls, value: object) -> str:
        """Return a validated Streamlit sidebar initial state."""
        return normalize_choice(
            value,
            field_name="streamlit_initial_sidebar_state",
            choices=STREAMLIT_SIDEBAR_STATE_NAMES,
            case="lower",
        )

    @field_validator("streamlit_page_title", "streamlit_service_name", mode="before")
    @classmethod
    def normalize_streamlit_text(cls, value: object, info: ValidationInfo) -> str:
        """Return non-empty Streamlit display/service settings."""
        return normalize_non_blank(value, field_name=str(info.field_name))

    @field_validator(
        "streamlit_i18n_file",
        "streamlit_css_file",
        "streamlit_screens_file",
        mode="before",
    )
    @classmethod
    def normalize_streamlit_optional_file(cls, value: object) -> str:
        """Return an optional Streamlit resource override file path."""
        return "" if value is None else str(value).strip()

    @field_validator("streamlit_default_manual_player_id", mode="before")
    @classmethod
    def normalize_streamlit_player_id(cls, value: object) -> str:
        """Return the default Streamlit player id."""
        return normalize_non_blank(value, field_name="streamlit_default_manual_player_id")

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

    @field_validator("model", mode="before")
    @classmethod
    def normalize_llm_model(cls, value: object) -> str:
        """Return the configured LLM model name."""
        return normalize_non_blank(value, field_name="model")

    @field_validator("llm_base_url", mode="before")
    @classmethod
    def normalize_llm_base_url(cls, value: object) -> str:
        """Return the optional OpenAI-compatible provider base URL."""
        return "" if value is None else str(value).strip()

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

    @field_validator("game_default_narration_mode", mode="before")
    @classmethod
    def normalize_game_default_narration_mode(cls, value: object) -> str:
        """Return the configured default narration mode."""
        return normalize_choice(
            value,
            field_name="game_default_narration_mode",
            choices=NARRATION_MODE_CHOICES,
            case="lower",
        )

    @field_validator(
        "game_supported_agent_name",
        "game_default_setup_id",
        "game_default_setup_name",
        "game_setup_description_template",
        "game_role_names",
        "game_phase_names",
        "api_title",
        "api_service_name",
        "api_version",
        mode="before",
    )
    @classmethod
    def normalize_game_text(cls, value: object) -> str:
        """Return a stripped non-empty game configuration string."""
        return normalize_non_blank(value, field_name="game setting")

    @model_validator(mode="after")
    def validate_game_settings(self) -> Self:
        """Ensure game count defaults are internally consistent."""
        self._normalize_provider_base_url()
        self._validate_supabase_settings()
        if self.api_game_list_default_limit > self.api_game_list_max_limit:
            raise ValueError(
                message_field_must_be_le_field(
                    "api_game_list_default_limit",
                    "api_game_list_max_limit",
                )
            )
        if self.api_timeline_default_limit > self.api_timeline_max_limit:
            raise ValueError(
                message_field_must_be_le_field(
                    "api_timeline_default_limit",
                    "api_timeline_max_limit",
                )
            )
        if self.game_min_players > self.game_max_players:
            raise ValueError(message_game_min_players_le_max_players())
        if not self.game_min_players <= self.game_default_player_count <= self.game_max_players:
            raise ValueError(message_game_default_player_count_between())
        split_mapping(self.game_role_names, field_name="game_role_names")
        split_mapping(self.game_phase_names, field_name="game_phase_names")
        try:
            self.game_setup_description_template.format(
                min_players=self.game_min_players,
                max_players=self.game_max_players,
                default_player_count=self.game_default_player_count,
            )
        except (KeyError, ValueError) as exc:
            raise ValueError(message_game_setup_description_template_invalid()) from exc
        self._validate_llm_settings()
        self._validate_definition_settings()
        return self

    def _normalize_provider_base_url(self) -> None:
        """Clear provider-specific default base URLs after provider override."""
        if (
            self.llm_provider != LLM_PROVIDER_LMSTUDIO
            and "llm_base_url" not in self.model_fields_set
        ):
            self.llm_base_url = ""

    def _validate_llm_settings(self) -> None:
        """Ensure provider-specific LLM settings are complete."""
        if self.llm_provider == LLM_PROVIDER_LMSTUDIO and not self.llm_base_url:
            raise ValueError(message_settings_llm_base_url_required(LLM_PROVIDER_LMSTUDIO))
        if self.llm_provider == LLM_PROVIDER_OPENAI and not self.configured_openai_api_key:
            raise ValueError(message_settings_openai_api_key_required(LLM_PROVIDER_OPENAI))

    def _validate_definition_settings(self) -> None:
        """Ensure runtime definitions are loadable and match configured settings."""
        try:
            game_definitions = self.game_definitions
            _ = self.llm_definitions
            missing_counts = [
                player_count
                for player_count in range(self.game_min_players, self.game_max_players + 1)
                if player_count not in game_definitions.roles.default_role_counts
            ]
        except Exception as exc:
            raise ValueError(message_definition_settings_invalid(exc)) from exc
        if missing_counts:
            missing = ", ".join(str(player_count) for player_count in missing_counts)
            raise ValueError(message_role_definition_missing_player_counts(missing))

    def _validate_supabase_settings(self) -> None:
        """Ensure client-facing Supabase settings are provided as a pair."""
        has_url = bool(self.supabase_url)
        has_key = bool(self.supabase_publishable_key_value)
        if has_url != has_key:
            raise ValueError(MESSAGE_SUPABASE_CLIENT_SETTINGS_MUST_BE_PAIRED)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached interface settings."""
    return AppSettings()
