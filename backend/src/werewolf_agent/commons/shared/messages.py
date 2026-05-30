"""User-facing messages shared across layers."""

from __future__ import annotations

from collections.abc import Iterable

TITLE_INVALID_CONFIGURATION = "Invalid Configuration"
TITLE_REQUEST_VALIDATION_FAILED = "Request Validation Failed"
TITLE_API_UNAVAILABLE = "API Unavailable"
TITLE_RESOURCE_NOT_FOUND = "Resource Not Found"
TITLE_METHOD_NOT_ALLOWED = "Method Not Allowed"
TITLE_AUTHENTICATION_REQUIRED = "Authentication Required"
TITLE_AUTHORIZATION_FAILED = "Authorization Failed"
TITLE_HTTP_ERROR = "HTTP Error"
TITLE_INVALID_GAME_PHASE = "Invalid Game Phase"
TITLE_INVALID_GAME_ACTION = "Invalid Game Action"
TITLE_INVALID_AGENT_RESPONSE = "Invalid Agent Response"
TITLE_LLM_PROVIDER_UNAVAILABLE = "LLM Provider Unavailable"
TITLE_OBSERVATION_WRITE_FAILED = "Observation Write Failed"
TITLE_UNEXPECTED_INTERNAL_ERROR = "Unexpected Internal Error"

DETAIL_CONFIG_INVALID_VALUE = "The application configuration contains an invalid value."
DETAIL_REQUEST_VALIDATION_FAILED = "The request body or parameters failed validation."
DETAIL_API_UNAVAILABLE = "The API server could not be reached."
DETAIL_RESOURCE_NOT_FOUND = "The requested resource was not found."
DETAIL_METHOD_NOT_ALLOWED = "The requested HTTP method is not allowed."
DETAIL_AUTHENTICATION_REQUIRED = "Authentication is required for this operation."
DETAIL_AUTHORIZATION_FAILED = "The supplied credentials are not valid for this operation."
DETAIL_HTTP_ERROR = "The HTTP request could not be completed."
DETAIL_GAME_INVALID_PHASE = "The requested game operation is not valid in the current phase."
DETAIL_GAME_INVALID_ACTION = "The requested game action is not valid."
DETAIL_AGENT_INVALID_RESPONSE = "The agent response could not be validated."
DETAIL_LLM_PROVIDER_UNAVAILABLE = "The configured LLM provider is temporarily unavailable."
DETAIL_OBSERVATION_WRITE_FAILED = "The game event log could not be written."
DETAIL_INTERNAL_UNEXPECTED = "An unexpected internal error occurred."

MESSAGE_INVALID_APPLICATION_CONFIGURATION = "Invalid application configuration."
MESSAGE_INVALID_VALUE = "Invalid value."
MESSAGE_SETTINGS = "settings"
LOG_GAME_RUN_CREATED = "game.run.created"
LOG_GAME_RUN_STEPPED = "game.run.stepped"
LOG_GAME_RUNS_LISTED = "game.runs.listed"
LOG_GAME_TIMELINE_LISTED = "game.timeline.listed"
LOG_PRIVATE_OBSERVATION_RETURNED = "game.private_observation.returned"
LOG_PLAYER_ACTION_SUBMITTED = "game.manual_action.accepted"
LOG_CLI_APPLICATION_STARTED = "cli.application.started"
LOG_CLI_GAME_CREATED = "cli.game.created"
LOG_CLI_ACTION_SUBMITTED = "cli.action.submitted"
LOG_CLI_PLAY_COMPLETED = "cli.play.completed"
LOG_CLI_TIMELINE_POLLED = "cli.timeline.polled"
LOG_CLI_REPLAY_COMPLETED = "cli.replay.completed"
LOG_CLI_APPLICATION_ERROR_HANDLED = "cli.application_error.handled"
LOG_CLI_UNHANDLED_EXCEPTION = "cli.exception.unhandled"
LOG_SHARED_API_REQUEST_COMPLETED = "http.client.request.completed"
LOG_STREAMLIT_ACTION_SUBMITTED = "streamlit.action.submitted"
LOG_STREAMLIT_ADVANCE_UNTIL_INPUT_ITERATION = "streamlit.advance_until_input.iteration"
LOG_STREAMLIT_ADVANCE_UNTIL_INPUT_STARTED = "streamlit.advance_until_input.started"
LOG_STREAMLIT_ADVANCE_UNTIL_INPUT_STOPPED = "streamlit.advance_until_input.stopped"
LOG_STREAMLIT_APPLICATION_ERROR_HANDLED = "streamlit.application_error.handled"
LOG_STREAMLIT_CONNECTION_CHECKED = "streamlit.connection.checked"
LOG_STREAMLIT_GAME_CREATED = "streamlit.game.created"
LOG_STREAMLIT_RERUN_STARTED = "streamlit.rerun.started"
LOG_STREAMLIT_REFRESHED = "streamlit.screen.loaded"
MESSAGE_GAME_NOT_FOUND = "Game not found."
MESSAGE_GAME_RUN_NOT_FOUND_TEMPLATE = "Game run not found: {game_id}"
MESSAGE_UNSUPPORTED_AGENT_ACTION = "Unsupported agent action."
MESSAGE_UNSUPPORTED_HUMAN_PLAYER_COUNT = "Only one human player is supported."
MESSAGE_INVALID_CONTROL_TOKEN = "Invalid control token."
MESSAGE_HUMAN_PLAYER_ID_MUST_MATCH_PLAYERS = "human_player must match a generated player id."
MESSAGE_PLAYER_IS_NOT_MANUAL = "Player is not configured for manual control."
MESSAGE_EXPECTED_SPEECH_ACTION = "Expected a speech action."
MESSAGE_PLAYER_LIST_LENGTH_MUST_MATCH_CONFIG = (
    "Player list length must match game config player_count."
)
MESSAGE_FINISHED_GAMES_CANNOT_BE_ADVANCED = "Finished games cannot be advanced."
MESSAGE_GAME_ID_MUST_BE_VALID_UUID = "game_id must be a valid UUID."
MESSAGE_PLAYER_IDS_MUST_BE_UNIQUE = "Player ids must be unique."
MESSAGE_PLAYER_ID_VALUES_MUST_BE_UNIQUE = "player id values must be unique."
MESSAGE_PLAYER_ROLES_ALL_OR_NONE = "Either every player role must be set or none of them."
MESSAGE_EXPLICIT_ROLES_MUST_MATCH_ROLE_COUNTS = (
    "Explicit player roles must match game config role_counts."
)
MESSAGE_WEREWOLVES_CANNOT_ATTACK_WEREWOLF = "Werewolves cannot attack another werewolf."
MESSAGE_SEER_CANNOT_INSPECT_SELF = "Seer cannot inspect themself."
MESSAGE_UNSUPPORTED_NIGHT_ACTION = "Unsupported night action."
MESSAGE_EXPECTED_NIGHT_ACTION = "Expected a night action."
MESSAGE_CANNOT_INSPECT_UNASSIGNED_ROLE = "Cannot inspect a player before roles are assigned."
MESSAGE_SELF_VOTING_DISABLED = "Self-voting is disabled for this game."
MESSAGE_EXPECTED_VOTE_ACTION = "Expected a vote action."
MESSAGE_MAX_STEPS_MUST_BE_AT_LEAST_ONE = "max_steps must be at least 1."
MESSAGE_POLL_INTERVAL_MUST_BE_NON_NEGATIVE = "poll_interval must be zero or greater."
MESSAGE_OUTPUT_FORMAT_MUST_BE_VALID = "output format must be one of: table, json, jsonl."
MESSAGE_JSON_OUTPUT_CANNOT_FOLLOW = "Use jsonl output when following streamed timeline items."
MESSAGE_ROLE_COUNT_MUST_USE_EQUALS = "role count entries must use role=count syntax."
MESSAGE_ROLE_COUNT_MUST_BE_INTEGER = "role count values must be integers."
MESSAGE_API_RESPONSE_NOT_JSON = "api.invalid_response: API response was not valid JSON."
MESSAGE_API_RESPONSE_NOT_OBJECT = "api.invalid_response: API response was not a JSON object."
MESSAGE_API_RESPONSE_SCHEMA_MISMATCH = (
    "api.invalid_response: API response did not match the public schema."
)
MESSAGE_NO_VALID_VOTE_TARGETS = "no valid vote targets"
MESSAGE_NO_ATTACK_TARGETS = "no attack targets"
MESSAGE_NO_INSPECT_TARGETS = "no inspect targets"
MESSAGE_NO_GUARD_TARGETS = "no guard targets"
MESSAGE_ROLE_HAS_NO_NIGHT_ACTION = "role has no night action"
MESSAGE_OBSERVATION_BELONGS_TO_ANOTHER_PLAYER = "observation belongs to another player"
MESSAGE_PLAYER_IS_DEAD = "player is dead"
MESSAGE_MISSING_SPEECH_MESSAGE = "missing speech message"
MESSAGE_MISSING_VOTE_TARGET = "missing vote target"
MESSAGE_MISSING_ATTACK_TARGET = "missing attack target"
MESSAGE_MISSING_INSPECT_TARGET = "missing inspect target"
MESSAGE_MISSING_GUARD_TARGET = "missing guard target"
MESSAGE_EVENT_TYPE_MUST_NOT_BE_BLANK = "event_type must not be blank"
MESSAGE_DAY_MUST_BE_NON_NEGATIVE = "day must be zero or greater"
MESSAGE_PLAYER_COUNT_MUST_MATCH_PLAYERS = "player_count must match the number of players"
MESSAGE_PLAYER_COUNT_AT_LEAST_ONE = "player_count must be at least 1"
MESSAGE_DAY_SPEECH_TURNS_AT_LEAST_ONE = "day_speech_turns must be at least 1"
MESSAGE_ROLE_COUNTS_MUST_SUM_TO_PLAYER_COUNT = "role_counts must sum to player_count"
MESSAGE_ROLE_COUNTS_REQUIRE_WEREWOLF = "role_counts must include at least one werewolf"
MESSAGE_ROLE_COUNTS_REQUIRE_VILLAGE_SIDE = (
    "role_counts must include at least one village-side player"
)
MESSAGE_SPEECH_ACTION_REQUIRES_MESSAGE = "message is required for speech actions"
MESSAGE_SPEECH_ACTION_FORBIDS_TARGET = "target_id is not allowed for speech actions"
MESSAGE_PASS_ACTION_FORBIDS_PAYLOAD = "pass actions cannot include target_id or message"
MESSAGE_SPEECH_DECISION_REQUIRES_MESSAGE = "message is required for speech decisions"
MESSAGE_SPEECH_DECISION_FORBIDS_TARGET = "target_id is not allowed for speech decisions"
MESSAGE_PASS_DECISION_FORBIDS_PAYLOAD = "pass decisions cannot include target_id or message"


def message_field_must_be_string(field_name: str) -> str:
    """Return a string-type validation message."""
    return f"{field_name} must be a string"


def message_field_must_not_be_blank(field_name: str) -> str:
    """Return a non-blank validation message."""
    return f"{field_name} must not be blank"


def message_field_must_be_one_of(field_name: str, choices: Iterable[str]) -> str:
    """Return a finite-choice validation message."""
    return f"{field_name} must be one of: {', '.join(sorted(choices))}"


def message_mapping_item_must_use_separator(field_name: str, separator: str) -> str:
    """Return a key-value mapping syntax validation message."""
    return f"{field_name} items must use '{separator}' between key and value"


def message_game_default_player_count_between() -> str:
    """Return a settings consistency validation message."""
    return "game_default_player_count must be between game_min_players and game_max_players"


def message_game_min_players_le_max_players() -> str:
    """Return a settings consistency validation message."""
    return "game_min_players must be less than or equal to game_max_players"


def message_ruleset_description_template_invalid() -> str:
    """Return a ruleset description template validation message."""
    return (
        "game_ruleset_description_template must use only min_players, "
        "max_players, and default_player_count placeholders"
    )


def message_role_count_must_be_zero_or_greater(role_id: str) -> str:
    """Return a role count validation message."""
    return f"role_counts[{role_id}] must be zero or greater"


def message_target_required(action_type: str, subject: str) -> str:
    """Return a target-required validation message."""
    return f"target_id is required for {action_type} {subject}"


def message_message_not_allowed(action_type: str, subject: str) -> str:
    """Return a message-forbidden validation message."""
    return f"message is not allowed for {action_type} {subject}"


def message_unsupported_type(value: str, subject: str) -> str:
    """Return an unsupported-type validation message."""
    return f"unsupported {subject} type: {value}"


def message_expected_phase(expected: str, current: str) -> str:
    """Return a phase validation message."""
    return f"Expected phase {expected}, but current phase is {current}."


def message_unknown_player_id(player_id: str) -> str:
    """Return an unknown-player validation message."""
    return f"Unknown player id: {player_id}."


def message_player_not_alive(player_id: str) -> str:
    """Return a dead-player validation message."""
    return f"Player is not alive: {player_id}."


def message_player_cannot_perform_role_action(player_id: str, role_id: str) -> str:
    """Return a role-action validation message."""
    return f"Player {player_id} cannot perform a {role_id} action."


def message_cannot_advance_phase(phase: str) -> str:
    """Return a phase-advance validation message."""
    return f"Cannot advance phase from {phase}."


def message_no_action_for_phase(phase: str) -> str:
    """Return an automated-agent no-action reason."""
    return f"no action for {phase}"


def message_player_count_between(min_players: int, max_players: int) -> str:
    """Return a player-count validation message."""
    return f"player_count must be between {min_players} and {max_players}."


def message_supported_agent_type_only(supported_agent_type: str) -> str:
    """Return an unsupported top-level agent validation message."""
    return f"Only {supported_agent_type} agent type is supported."


def message_supported_player_agent_type_only(supported_agent_type: str) -> str:
    """Return an unsupported player agent validation message."""
    return f"Only {supported_agent_type} agent_type is supported."


def message_unsupported_llm_provider(provider: str) -> str:
    """Return an unsupported LLM provider configuration message."""
    return f"Unsupported LLM provider: {provider}."


def message_game_did_not_complete(max_steps: int) -> str:
    """Return a CLI max-step failure message."""
    return f"Game did not complete within {max_steps} API steps."


def message_game_run_not_found(game_id: object) -> str:
    """Return an internal persistence missing-row message."""
    return MESSAGE_GAME_RUN_NOT_FOUND_TEMPLATE.format(game_id=game_id)


def message_api_unavailable(error: object) -> str:
    """Return an API connectivity failure message."""
    return f"api.unavailable: Could not connect to API ({error})."


def message_api_http_error(status_code: int) -> str:
    """Return an HTTP status failure message."""
    return f"api.http_error: API request failed with HTTP {status_code}."


def message_problem_detail(code: str, detail: str) -> str:
    """Return a CLI-safe Problem Details summary."""
    return f"{code}: {detail}"


def message_error_line(detail: str, suffix: str = "") -> str:
    """Return one CLI error line."""
    return f"Error: {detail}{suffix}"


def message_invalid_configuration_for(location: str, message: str) -> str:
    """Return a settings validation detail."""
    return f"Invalid configuration for {location}: {message}"
