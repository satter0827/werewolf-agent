"""application messagesが所有する文言."""

from __future__ import annotations

from collections.abc import Iterable

MESSAGE_MANUAL_PLAYER_ID_MUST_MATCH_PLAYERS = "manual_player_id must match a generated player id."

MESSAGE_PLAYER_AUTHENTICATION_REQUIRED = "Authenticated player context is required."

MESSAGE_PLAYER_IS_NOT_MANUAL = "Player is not configured for manual control."

MESSAGE_MANUAL_INPUT_REQUIRED = "Manual player input is required before advancing."

MESSAGE_FINISHED_GAMES_CANNOT_BE_ADVANCED = "Finished games cannot be advanced."

MESSAGE_ADVANCE_JOB_STATE_CHANGED = "Game changed while advance job was running."

MESSAGE_PREPARED_TRANSITION_STATE_MISMATCH = "Prepared domain transition state is inconsistent."

MESSAGE_GAME_ID_MUST_BE_VALID_UUID = "game_id must be a valid UUID."

MESSAGE_PLAYER_COUNT_AT_LEAST_ONE = "player_count must be at least 1"

MESSAGE_MIN_PLAYERS_MUST_BE_AT_LEAST_ONE = "min_players must be at least 1"

MESSAGE_MAX_PLAYERS_MUST_BE_GE_MIN_PLAYERS = (
    "max_players must be greater than or equal to min_players"
)

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


def message_unknown_scenario(scenario_id: str) -> str:
    """Return an unknown scenario message."""
    return f"Unknown scenario: {scenario_id}"


MESSAGE_ROLE_ABILITIES_MUST_BE_UNIQUE = "role abilities must be unique"

MESSAGE_NARRATION_TEMPLATES_REQUIRED = "narration templates must include at least one value"


def message_definition_references_unknown_ids(
    source: str,
    target: str,
    identifiers: Iterable[str],
) -> str:
    """Return a cross-resource definition reference error."""
    return f"{source} references unknown {target}: {', '.join(sorted(identifiers))}"
