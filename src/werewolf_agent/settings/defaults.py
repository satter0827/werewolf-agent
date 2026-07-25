"""Packaged runtime defaults grouped independently from process settings."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Final, Literal

from werewolf_agent.settings.constants import (
    CLI_OUTPUT_FORMAT_CHOICE_SET,
    LLM_FALLBACK_POLICY_CHOICE_SET,
    LLM_PROVIDER_CHOICE_SET,
    LLM_STRUCTURED_OUTPUT_MODE_CHOICE_SET,
    LOG_OUTPUT_CHOICE_SET,
)
from werewolf_agent.settings.loading import load_packaged_defaults
from werewolf_agent.settings.messages import message_missing_default_setting

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

DEFAULT_GENERATED_DIR: Final = _path_default("generated_dir")
DEFAULT_LLM_PROVIDER: Final = _string_default("llm_provider")
DEFAULT_LLM_MODEL: Final = _string_default("model")
DEFAULT_LLM_BASE_URL: Final = _string_default("llm_base_url")
DEFAULT_LLM_TIMEOUT_SECONDS: Final = _float_default("llm_timeout_seconds")
DEFAULT_LLM_MAX_RETRIES: Final = _integer_default("llm_max_retries")
DEFAULT_LLM_MAX_TOKENS: Final = _integer_default("llm_max_tokens")
DEFAULT_LLM_TEMPERATURE: Final = _float_default("llm_temperature")
DEFAULT_LLM_DEFAULT_AGENT_STRATEGY_ID: Final = _string_default("llm_default_agent_strategy_id")
DEFAULT_LLM_DECISION_GRAPHS_FILE: Final = _string_default("llm_decision_graphs_file")
DEFAULT_LLM_STRUCTURED_OUTPUT_MODE: Final = _string_default("llm_structured_output_mode")
DEFAULT_LLM_VALIDATION_RETRY_COUNT: Final = _integer_default("llm_validation_retry_count")
DEFAULT_LLM_GRAPH_MAX_STEPS: Final = _integer_default("llm_graph_max_steps")
DEFAULT_LLM_FALLBACK_POLICY: Final = _string_default("llm_fallback_policy")
DEFAULT_LLM_PROMPT_FILE: Final = _string_default("llm_prompt_file")
DEFAULT_LLM_FAKE_RESPONSES_FILE: Final = _string_default("llm_fake_responses_file")
DEFAULT_LLM_PLAYERS_FILE: Final = _string_default("llm_players_file")
DEFAULT_WORKER_PAID_LLM_PROVIDER: Final = _string_default("worker_paid_llm_provider")
DEFAULT_WORKER_PAID_LLM_MODEL: Final = _string_default("worker_paid_llm_model")
DEFAULT_WORKER_PAID_LLM_BASE_URL: Final = _string_default("worker_paid_llm_base_url")
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
DEFAULT_STREAMLIT_PAGE_TITLE: Final = _string_default("streamlit_page_title")
DEFAULT_STREAMLIT_SERVICE_NAME: Final = _string_default("streamlit_service_name")
DEFAULT_REVEAL_API_ENABLED: Final = _bool_default("reveal_api_enabled")
DEFAULT_API_GAME_LIST_DEFAULT_LIMIT: Final = _integer_default("api_game_list_default_limit")
DEFAULT_API_GAME_LIST_MAX_LIMIT: Final = _integer_default("api_game_list_max_limit")
DEFAULT_API_TIMELINE_DEFAULT_LIMIT: Final = _integer_default("api_timeline_default_limit")
DEFAULT_API_TIMELINE_MAX_LIMIT: Final = _integer_default("api_timeline_max_limit")
DEFAULT_API_HOST: Final = _string_default("api_host")
DEFAULT_API_PORT: Final = _integer_default("api_port")
DEFAULT_API_BASE_URL: Final = _string_default("api_base_url")
DEFAULT_API_CONTRACT_VERSION: Final = _string_default("api_contract_version")
DEFAULT_API_CONFIG_REVISION: Final = _string_default("api_config_revision")
DEFAULT_API_DOCS_ENABLED: Final = _bool_default("api_docs_enabled")
DEFAULT_API_CORS_ORIGINS: Final = _string_default("api_cors_origins")
DEFAULT_API_MAX_BODY_BYTES: Final = _integer_default("api_max_body_bytes")
DEFAULT_API_MESSAGE_MAX_CHARS: Final = _integer_default("api_message_max_chars")
DEFAULT_API_RATE_LIMIT_REQUESTS: Final = _integer_default("api_rate_limit_requests")
DEFAULT_API_RATE_LIMIT_WINDOW_SECONDS: Final = _integer_default("api_rate_limit_window_seconds")
DEFAULT_API_TIMEOUT_SECONDS: Final = _float_default("api_timeout_seconds")
DEFAULT_API_MAX_CONCURRENT_REQUESTS: Final = _integer_default("api_max_concurrent_requests")
DEFAULT_UI_THEME_ID: Final = _string_default("ui_theme_id")
DEFAULT_UI_SPACING_UNIT: Final = _integer_default("ui_spacing_unit")
DEFAULT_UI_DESKTOP_BREAKPOINT: Final = _integer_default("ui_desktop_breakpoint")
DEFAULT_UI_MOTION: Final = _string_default("ui_motion")
DEFAULT_UI_DEFAULT_MANUAL_PLAYER_ID: Final = _string_default("ui_default_manual_player_id")
DEFAULT_UI_DEFAULT_SETUP_SEED: Final = _string_default("ui_default_setup_seed")
DEFAULT_UI_OPERATION_POLL_INTERVAL_MS: Final = _integer_default("ui_operation_poll_interval_ms")
DEFAULT_UI_OPERATION_POLL_TIMEOUT_MS: Final = _integer_default("ui_operation_poll_timeout_ms")
DEFAULT_SUPABASE_JWT_AUDIENCE: Final = _string_default("supabase_jwt_audience")
DEFAULT_SUPABASE_JWT_ISSUER: Final = _string_default("supabase_jwt_issuer")
DEFAULT_SUPABASE_JWKS_URL: Final = _string_default("supabase_jwks_url")
DEFAULT_GAME_MIN_PLAYERS: Final = _integer_default("game_min_players")
DEFAULT_GAME_MAX_PLAYERS: Final = _integer_default("game_max_players")
DEFAULT_GAME_DEFAULT_PLAYER_COUNT: Final = _integer_default("game_default_player_count")
DEFAULT_GAME_SUPPORTED_AGENT_TYPE: Final = _string_default("game_supported_agent_type")
DEFAULT_GAME_SUPPORTED_AGENT_NAME: Final = _string_default("game_supported_agent_name")
DEFAULT_GAME_DEFAULT_NARRATION_MODE: Final = _string_default("game_default_narration_mode")
DEFAULT_GAME_DEFAULT_SETUP_PRESET_ID: Final = _string_default("game_default_setup_preset_id")
DEFAULT_GAME_RULES_FILE: Final = _string_default("game_rules_file")
DEFAULT_GAME_ROLES_FILE: Final = _string_default("game_roles_file")
DEFAULT_GAME_CATALOG_FILE: Final = _string_default("game_catalog_file")
DEFAULT_GAME_ABILITIES_FILE: Final = _string_default("game_abilities_file")
DEFAULT_GAME_SETUP_DESCRIPTION_TEMPLATE: Final = _string_default("game_setup_description_template")
DEFAULT_GAME_ROLE_NAMES: Final = _string_default("game_role_names")
DEFAULT_GAME_PHASE_NAMES: Final = _string_default("game_phase_names")

LOG_LEVEL_NAMES: Final = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
LOG_OUTPUT_NAMES: Final = LOG_OUTPUT_CHOICE_SET
CLI_OUTPUT_FORMAT_NAMES: Final = CLI_OUTPUT_FORMAT_CHOICE_SET
STREAMLIT_LANGUAGE_NAMES: Final = frozenset({"ja", "en"})
STREAMLIT_SIDEBAR_STATE_NAMES: Final = frozenset({"auto", "expanded", "collapsed"})
LLM_PROVIDER_NAMES: Final = LLM_PROVIDER_CHOICE_SET
LLM_STRUCTURED_OUTPUT_MODE_NAMES: Final = LLM_STRUCTURED_OUTPUT_MODE_CHOICE_SET
LLM_FALLBACK_POLICY_NAMES: Final = LLM_FALLBACK_POLICY_CHOICE_SET
SUPPORTED_AGENT_TYPE_NAMES: Final = frozenset({DEFAULT_GAME_SUPPORTED_AGENT_TYPE})

StreamlitLanguage = Literal["ja", "en"]
StreamlitSidebarState = Literal["auto", "expanded", "collapsed"]
UiMotion = Literal["system", "reduced"]
