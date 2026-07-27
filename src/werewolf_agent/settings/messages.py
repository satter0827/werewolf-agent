"""Runtime setting validation messages."""

from __future__ import annotations

from collections.abc import Iterable

MESSAGE_INVALID_APPLICATION_CONFIGURATION = "Invalid application configuration."

MESSAGE_INVALID_VALUE = "Invalid value."

MESSAGE_SETTINGS = "settings"


MESSAGE_ROLE_ABILITIES_MUST_BE_UNIQUE = "role abilities must be unique"

MESSAGE_NARRATION_TEMPLATES_REQUIRED = "narration templates must include at least one value"

MESSAGE_LOG_FILE_NAME_MUST_BE_FILE_NAME = "log_file_name must be a file name"

MESSAGE_SUPABASE_URL_MUST_START_WITH_HTTP = "supabase_url must start with http:// or https://"

MESSAGE_SUPABASE_CLIENT_SETTINGS_MUST_BE_PAIRED = (
    "WEREWOLF_SUPABASE_URL and WEREWOLF_SUPABASE_PUBLISHABLE_KEY must be set together."
)


def message_field_must_be_string(field_name: str) -> str:
    """Return a string-type validation message."""
    return f"{field_name} must be a string"


def message_field_must_not_be_blank(field_name: str) -> str:
    """Return a non-blank validation message."""
    return f"{field_name} must not be blank"


def message_field_must_be_one_of(field_name: str, choices: Iterable[str]) -> str:
    """Return a finite-choice validation message."""
    return f"{field_name} must be one of: {', '.join(sorted(choices))}"


def message_field_must_be_le_field(field_name: str, maximum_field_name: str) -> str:
    """Return a less-than-or-equal field-pair validation message."""
    return f"{field_name} must be less than or equal to {maximum_field_name}"


def message_mapping_item_must_use_separator(field_name: str, separator: str) -> str:
    """Return a key-value mapping syntax validation message."""
    return f"{field_name} items must use '{separator}' between key and value"


def message_game_min_players_le_max_players() -> str:
    """Return a settings consistency validation message."""
    return "game_min_players must be less than or equal to game_max_players"


def message_missing_default_setting(key: str) -> str:
    """Return a packaged default lookup failure message."""
    return f"Missing default setting: {key}"


def message_definition_settings_invalid(error: object) -> str:
    """Return a runtime definition settings validation message."""
    return f"definition settings are invalid: {error}"


def message_definition_references_unknown_ids(
    source: str,
    target: str,
    identifiers: Iterable[str],
) -> str:
    """Return a cross-resource definition reference error."""
    return f"{source} references unknown {target}: {', '.join(sorted(identifiers))}"


def message_settings_llm_base_url_required(provider: str) -> str:
    """Return a settings-level LLM base URL requirement message."""
    return f"WEREWOLF_LLM_BASE_URL is required when WEREWOLF_LLM_PROVIDER={provider}"


def message_settings_openai_api_key_required(provider: str) -> str:
    """Return a settings-level OpenAI API key requirement message."""
    return f"OPENAI_API_KEY is required when WEREWOLF_LLM_PROVIDER={provider}"


def message_invalid_configuration_for(location: str, message: str) -> str:
    """Return a settings validation detail."""
    return f"Invalid configuration for {location}: {message}"
