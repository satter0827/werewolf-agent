"""application messagesが所有する文言."""

from __future__ import annotations

from collections.abc import Iterable

MESSAGE_MANUAL_PLAYER_ID_MUST_MATCH_PLAYERS = "manual_player_id must match a generated player id."

MESSAGE_PLAYER_AUTHENTICATION_REQUIRED = "Authenticated player context is required."

MESSAGE_PLAYER_IS_NOT_MANUAL = "Player is not configured for manual control."

MESSAGE_MANUAL_INPUT_REQUIRED = "Manual player input is required before advancing."

MESSAGE_FINISHED_GAMES_CANNOT_BE_ADVANCED = "Finished games cannot be advanced."

MESSAGE_ADVANCE_JOB_STATE_CHANGED = "Game changed while advance job was running."

MESSAGE_GAME_ID_MUST_BE_VALID_UUID = "game_id must be a valid UUID."

MESSAGE_PLAYER_COUNT_AT_LEAST_ONE = "player_count must be at least 1"

MESSAGE_CHARACTER_ASSIGNMENTS_KEYS_MUST_MATCH_PLAYERS = (
    "character_assignments keys must match generated player ids"
)

MESSAGE_CHARACTER_ASSIGNMENTS_VALUES_MUST_BE_UNIQUE = "character_assignments values must be unique"

MESSAGE_CUSTOM_ROLE_IDS_MUST_BE_UNIQUE = "custom role ids must be unique"

MESSAGE_CUSTOM_CHARACTER_IDS_MUST_BE_UNIQUE = "custom character ids must be unique"

MESSAGE_CUSTOM_ROLES_CONFLICT_WITH_DEFAULT_ROLE_IDS = "custom roles conflict with default role ids"

MESSAGE_CUSTOM_ROLES_CONTAIN_UNKNOWN_ABILITIES = "custom roles contain unknown abilities"

MESSAGE_CUSTOM_CHARACTERS_CONFLICT_WITH_DEFAULT_CHARACTER_IDS = (
    "custom characters conflict with default character ids"
)

MESSAGE_CUSTOM_CHARACTERS_CONFLICT_WITH_PLAYER_ROSTER = (
    "custom characters conflict with player roster"
)

MESSAGE_CHARACTER_ASSIGNMENTS_CONTAIN_UNKNOWN_GENERATED_PLAYER_IDS = (
    "character assignments contain unknown generated player ids"
)

MESSAGE_CHARACTER_ASSIGNMENTS_CONTAIN_UNKNOWN_CHARACTER_IDS = (
    "character assignments contain unknown character ids"
)

MESSAGE_PLAYER_ROSTER_NOT_ENOUGH_ENABLED_PLAYERS = (
    "player roster does not have enough enabled players"
)

MESSAGE_MIN_PLAYERS_MUST_BE_AT_LEAST_ONE = "min_players must be at least 1"

MESSAGE_MAX_PLAYERS_MUST_BE_GE_MIN_PLAYERS = (
    "max_players must be greater than or equal to min_players"
)

MESSAGE_DEFAULT_PLAYER_COUNT_WITHIN_MIN_MAX = "default_player_count must be within min/max players"

MESSAGE_DEFAULT_NARRATION_MODE_UNSUPPORTED = "default_narration_mode is not supported"

MESSAGE_GAME_LIST_DEFAULT_LIMIT_MUST_BE_AT_LEAST_ONE = "game_list_default_limit must be at least 1"

MESSAGE_GAME_LIST_MAX_LIMIT_MUST_BE_AT_LEAST_ONE = "game_list_max_limit must be at least 1"

MESSAGE_GAME_LIST_DEFAULT_LIMIT_MUST_NOT_EXCEED_MAX = (
    "game_list_default_limit must not exceed game_list_max_limit"
)

MESSAGE_TIMELINE_DEFAULT_LIMIT_MUST_BE_AT_LEAST_ONE = "timeline_default_limit must be at least 1"

MESSAGE_TIMELINE_MAX_LIMIT_MUST_BE_AT_LEAST_ONE = "timeline_max_limit must be at least 1"

MESSAGE_TIMELINE_DEFAULT_LIMIT_MUST_NOT_EXCEED_MAX = (
    "timeline_default_limit must not exceed timeline_max_limit"
)


def message_field_must_be_between(field_name: str, minimum: object, maximum: object) -> str:
    """Return an inclusive range validation message."""
    return f"{field_name} must be between {minimum} and {maximum}"


def message_unsupported_action_type(value: str) -> str:
    """Return an unsupported action type validation message."""
    return f"Unsupported action type: {value}"


def message_player_count_between(min_players: int, max_players: int) -> str:
    """Return a player-count validation message."""
    return f"player_count must be between {min_players} and {max_players}."


def message_unknown_setup_preset(preset_id: str) -> str:
    """Return an unknown setup preset message."""
    return f"Unknown setup preset: {preset_id}"


def message_unknown_scenario(scenario_id: str) -> str:
    """Return an unknown scenario message."""
    return f"Unknown scenario: {scenario_id}"


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


def message_default_role_counts_unknown_roles(role_ids: Iterable[str]) -> str:
    """Return an unknown-role validation message for default role counts."""
    return f"default_role_counts contain unknown roles: {', '.join(role_ids)}"


def message_default_role_counts_must_sum(player_count: int) -> str:
    """Return a default role-count sum validation message."""
    return f"default_role_counts[{player_count}] must sum to {player_count}"


def message_default_role_counts_must_define_player_count(player_count: int) -> str:
    """Return a default role-count coverage validation message."""
    return f"default_role_counts must define player_count {player_count}"


def message_definition_references_unknown_ids(
    source: str,
    target: str,
    identifiers: Iterable[str],
) -> str:
    """Return a cross-resource definition reference error."""
    return f"{source} references unknown {target}: {', '.join(sorted(identifiers))}"
