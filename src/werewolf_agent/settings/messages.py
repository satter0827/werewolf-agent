"""Runtime setting validation messages."""

from __future__ import annotations

from collections.abc import Iterable

MESSAGE_INVALID_APPLICATION_CONFIGURATION = "Invalid application configuration."

MESSAGE_INVALID_VALUE = "Invalid value."

MESSAGE_SETTINGS = "settings"

MESSAGE_GENERATED_PLAYER_INDEX_MUST_BE_AT_LEAST_ONE = "generated player index must be at least 1"

MESSAGE_ROLE_ABILITIES_MUST_BE_UNIQUE = "role abilities must be unique"

MESSAGE_CUSTOM_ROLE_ABILITIES_MUST_BE_UNIQUE = "custom role abilities must be unique"

MESSAGE_NARRATION_TEMPLATES_REQUIRED = "narration templates must include at least one value"

MESSAGE_ALLOWED_ROLES_MUST_BE_UNIQUE = "allowed_roles must be unique"

MESSAGE_SETUP_PRESET_ROLE_COUNTS_REQUIRED = (
    "setup preset role_counts must include at least one player"
)

MESSAGE_ROLES_REQUIRED = "roles must include at least one role"

MESSAGE_DEFAULT_ROLE_COUNTS_REQUIRED = "default_role_counts must include at least one player count"

MESSAGE_DEFAULT_ROLE_COUNT_KEYS_POSITIVE = "default_role_counts keys must be positive player counts"

MESSAGE_PLAYERS_REQUIRED = "players must include at least one enabled profile"

MESSAGE_PLAYER_PROFILE_NAMES_MUST_BE_UNIQUE = "player profile names must be unique"

MESSAGE_PROMPT_MESSAGE_ROLE_MUST_BE_VALID = "prompt message role must be one of: ai, human, system"

MESSAGE_INPUT_VARIABLES_REQUIRED = "input_variables must include at least one value"

MESSAGE_INPUT_VARIABLES_MUST_BE_UNIQUE = "input_variables must be unique"

MESSAGE_PROMPT_MESSAGES_REQUIRED = "messages must include at least one prompt message"

MESSAGE_RESPONSE_FORMAT_SCHEMA_MUST_BE_AGENT_DECISION = (
    "response_format.schema must be AgentDecision"
)

MESSAGE_FAKE_DECISION_PASS_TEMPLATE_REQUIRED = "templates.pass is required"

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


def message_game_default_player_count_between() -> str:
    """Return a settings consistency validation message."""
    return "game_default_player_count must be between game_min_players and game_max_players"


def message_game_min_players_le_max_players() -> str:
    """Return a settings consistency validation message."""
    return "game_min_players must be less than or equal to game_max_players"


def message_game_setup_description_template_invalid() -> str:
    """Return a game setup description template validation message."""
    return (
        "game_setup_description_template must use only min_players, "
        "max_players, and default_player_count placeholders"
    )


def message_missing_default_setting(key: str) -> str:
    """Return a packaged default lookup failure message."""
    return f"Missing default setting: {key}"


def message_definition_settings_invalid(error: object) -> str:
    """Return a runtime definition settings validation message."""
    return f"definition settings are invalid: {error}"


def message_role_definition_missing_player_counts(missing: str) -> str:
    """Return a role definition default-count coverage message."""
    return (
        f"game role definition default_role_counts must define configured player counts: {missing}"
    )


def message_default_role_counts_unknown_roles(role_ids: Iterable[str]) -> str:
    """Return an unknown-role validation message for default role counts."""
    return f"default_role_counts contain unknown roles: {', '.join(role_ids)}"


def message_default_role_counts_must_sum(player_count: int) -> str:
    """Return a default role-count sum validation message."""
    return f"default_role_counts[{player_count}] must sum to {player_count}"


def message_default_role_counts_must_define_player_count(player_count: int) -> str:
    """Return a default role-count coverage validation message."""
    return f"default_role_counts must define player_count {player_count}"


def message_unknown_setup_preset(preset_id: str) -> str:
    """Return an unknown setup preset message."""
    return f"Unknown setup preset: {preset_id}"


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


def message_input_variables_not_used(names: str) -> str:
    """Return a prompt-template unused variable message."""
    return f"input_variables not used by messages: {names}"


def message_message_variables_missing(names: str) -> str:
    """Return a prompt-template missing variable message."""
    return f"message variables missing from input_variables: {names}"


def message_fake_decision_templates_required(action_type: str) -> str:
    """Return a FakeListLLM template coverage message."""
    return f"templates.{action_type} must include at least one item"


def message_invalid_configuration_for(location: str, message: str) -> str:
    """Return a settings validation detail."""
    return f"Invalid configuration for {location}: {message}"
