"""Environment-backed settings for interfaces and adapters."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import (
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from werewolf_agent.settings.constants import (
    LLM_PROVIDER_LMSTUDIO,
    LLM_PROVIDER_OPENAI,
    NARRATION_MODE_CHOICES,
)
from werewolf_agent.settings.defaults import (
    CLI_OUTPUT_FORMAT_NAMES,
    LLM_FALLBACK_POLICY_NAMES,
    LLM_PROVIDER_NAMES,
    LLM_STRUCTURED_OUTPUT_MODE_NAMES,
    LOG_LEVEL_NAMES,
    LOG_OUTPUT_NAMES,
    STREAMLIT_LANGUAGE_NAMES,
    STREAMLIT_SIDEBAR_STATE_NAMES,
    SUPPORTED_AGENT_TYPE_NAMES,
)
from werewolf_agent.settings.messages import (
    MESSAGE_LOG_FILE_NAME_MUST_BE_FILE_NAME,
    MESSAGE_SUPABASE_CLIENT_SETTINGS_MUST_BE_PAIRED,
    MESSAGE_SUPABASE_URL_MUST_START_WITH_HTTP,
    message_field_must_be_le_field,
    message_game_default_player_count_between,
    message_game_min_players_le_max_players,
    message_game_setup_description_template_invalid,
    message_mapping_item_must_use_separator,
    message_settings_llm_base_url_required,
    message_settings_openai_api_key_required,
)
from werewolf_agent.settings.sections import (
    ApiSettings,
    CliSettings,
    DatabaseSettings,
    GameSettings,
    LlmSettings,
    LoggingSettings,
    StreamlitSettings,
    WorkerSettings,
)
from werewolf_agent.settings.validation import normalize_choice, normalize_non_blank


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


class AppSettings(
    LlmSettings,
    LoggingSettings,
    DatabaseSettings,
    WorkerSettings,
    CliSettings,
    StreamlitSettings,
    GameSettings,
    ApiSettings,
    BaseSettings,
):
    """Settings loaded by entry points and injected inward."""

    model_config = SettingsConfigDict(
        env_file=repository_root() / ".env",
        env_file_encoding="utf-8",
        env_prefix="WEREWOLF_",
        extra="ignore",
        populate_by_name=True,
    )

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
    def api_cors_origin_values(self) -> list[str]:
        """Return configured browser origins."""
        return split_csv(self.api_cors_origins)

    @property
    def resolved_supabase_jwt_issuer(self) -> str:
        """Return the expected Supabase JWT issuer."""
        configured = self.supabase_jwt_issuer.strip()
        return configured or f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def resolved_supabase_jwks_url(self) -> str:
        """Return the Supabase JWKS endpoint used for key rotation."""
        configured = self.supabase_jwks_url.strip()
        return configured or f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

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
    def llm_decision_graphs_path(self) -> Path | None:
        """Return the configured external LLM decision graph file, if any."""
        return _optional_repository_path(self.llm_decision_graphs_file)

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

    @property
    def game_abilities_path(self) -> Path | None:
        """Return the configured external ability definition file, if any."""
        return _optional_repository_path(self.game_abilities_file)

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

    @field_validator("llm_default_agent_strategy_id", mode="before")
    @classmethod
    def normalize_llm_default_agent_strategy_id(cls, value: object) -> str:
        """Return the default LLM agent strategy id."""
        return normalize_non_blank(value, field_name="llm_default_agent_strategy_id")

    @field_validator(
        "llm_prompt_file",
        "llm_fake_responses_file",
        "llm_players_file",
        "llm_decision_graphs_file",
        mode="before",
    )
    @classmethod
    def normalize_llm_optional_file(cls, value: object) -> str:
        """Return an optional LLM resource override file path."""
        return "" if value is None else str(value).strip()

    @field_validator("llm_structured_output_mode", mode="before")
    @classmethod
    def normalize_llm_structured_output_mode(cls, value: object) -> str:
        """Return a validated structured-output mode."""
        return normalize_choice(
            value,
            field_name="llm_structured_output_mode",
            choices=LLM_STRUCTURED_OUTPUT_MODE_NAMES,
            case="lower",
        )

    @field_validator("llm_fallback_policy", mode="before")
    @classmethod
    def normalize_llm_fallback_policy(cls, value: object) -> str:
        """Return a validated fallback policy."""
        return normalize_choice(
            value,
            field_name="llm_fallback_policy",
            choices=LLM_FALLBACK_POLICY_NAMES,
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
        "game_default_setup_preset_id",
        "game_setup_description_template",
        "game_role_names",
        "game_phase_names",
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

    def _validate_supabase_settings(self) -> None:
        """Ensure client-facing Supabase settings are provided as a pair."""
        has_url = bool(self.supabase_url)
        has_key = bool(self.supabase_publishable_key_value)
        if has_url != has_key:
            raise ValueError(MESSAGE_SUPABASE_CLIENT_SETTINGS_MUST_BE_PAIRED)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached application settings."""
    return AppSettings()
