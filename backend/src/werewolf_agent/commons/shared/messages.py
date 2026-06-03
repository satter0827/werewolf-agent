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
LOG_GAME_CREATED = "game.created"
LOG_GAME_ADVANCE_JOB_COMPLETED = "game.advance_job.completed"
LOG_GAME_ADVANCE_JOB_FAILED = "game.advance_job.failed"
LOG_GAME_ADVANCE_JOB_STARTED = "game.advance_job.started"
LOG_GAME_STEPPED = "game.stepped"
LOG_GAMES_LISTED = "games.listed"
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
LOG_STREAMLIT_ADVANCE_STEP_COMPLETED = "streamlit.advance_step.completed"
LOG_STREAMLIT_ADVANCE_STEP_STARTED = "streamlit.advance_step.started"
LOG_STREAMLIT_APPLICATION_ERROR_HANDLED = "streamlit.application_error.handled"
LOG_STREAMLIT_GAME_CREATED = "streamlit.game.created"
LOG_STREAMLIT_RERUN_STARTED = "streamlit.rerun.started"
LOG_STREAMLIT_REFRESHED = "streamlit.screen.loaded"
MESSAGE_GAME_NOT_FOUND = "Game not found."
MESSAGE_GAME_NOT_FOUND_TEMPLATE = "Game not found: {game_id}"
MESSAGE_UNSUPPORTED_AGENT_ACTION = "Unsupported agent action."
MESSAGE_UNSUPPORTED_MANUAL_PLAYER_COUNT = "Only one manual player is supported."
MESSAGE_INVALID_MANUAL_TOKEN = "Invalid manual token."
MESSAGE_MANUAL_PLAYER_ID_MUST_MATCH_PLAYERS = "manual_player_id must match a generated player id."
MESSAGE_PLAYER_IS_NOT_MANUAL = "Player is not configured for manual control."
MESSAGE_EXPECTED_SPEECH_ACTION = "Expected a speech action."
MESSAGE_MANUAL_INPUT_REQUIRED = "Manual player input is required before advancing."
MESSAGE_PLAYER_LIST_LENGTH_MUST_MATCH_CONFIG = (
    "Player list length must match game config player_count."
)
MESSAGE_FINISHED_GAMES_CANNOT_BE_ADVANCED = "Finished games cannot be advanced."
MESSAGE_ADVANCE_JOB_NOT_FOUND = "Advance job not found."
MESSAGE_ADVANCE_JOB_FAILED = "Advance job failed."
MESSAGE_ADVANCE_JOB_RESULT_MISSING = "Advance job completed without a result."
MESSAGE_ADVANCE_JOB_STATE_CHANGED = "Game changed while advance job was running."
MESSAGE_GAME_ID_MUST_BE_VALID_UUID = "game_id must be a valid UUID."
MESSAGE_PLAYER_IDS_MUST_BE_UNIQUE = "Player ids must be unique."
MESSAGE_PLAYER_ID_VALUES_MUST_BE_UNIQUE = "player id values must be unique."
MESSAGE_PLAYER_ROLES_ALL_OR_NONE = "Either every player role must be set or none of them."
MESSAGE_EXPLICIT_ROLES_MUST_MATCH_ROLE_COUNTS = (
    "Explicit player roles must match game config role_counts."
)
MESSAGE_WEREWOLVES_CANNOT_ATTACK_WEREWOLF = "Werewolves cannot attack another werewolf."
MESSAGE_SEER_CANNOT_INSPECT_SELF = "Seer cannot inspect themself."
MESSAGE_KNIGHT_CANNOT_GUARD_SELF = "knight cannot guard self"
MESSAGE_KNIGHT_CANNOT_REPEAT_GUARD_TARGET = (
    "knight cannot guard the same target on consecutive nights"
)
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
MESSAGE_INVALID_CREATE_GAME_REQUEST = "invalid create game request"
MESSAGE_API_RESPONSE_NOT_JSON = "api.invalid_response: API response was not valid JSON."
MESSAGE_API_RESPONSE_NOT_OBJECT = "api.invalid_response: API response was not a JSON object."
MESSAGE_API_RESPONSE_SCHEMA_MISMATCH = (
    "api.invalid_response: API response did not match the public schema."
)
MESSAGE_NO_VALID_VOTE_TARGETS = "no valid vote targets"
MESSAGE_NO_ATTACK_TARGETS = "no attack targets"
MESSAGE_NO_INSPECT_TARGETS = "no inspect targets"
MESSAGE_NO_GUARD_TARGETS = "no guard targets"
MESSAGE_NO_TARGET = "no target"
MESSAGE_ROLE_HAS_NO_NIGHT_ACTION = "role has no night action"
MESSAGE_OBSERVATION_BELONGS_TO_ANOTHER_PLAYER = "observation belongs to another player"
MESSAGE_PLAYER_IS_DEAD = "player is dead"
MESSAGE_LLM_DECISION_PLAYER_MISMATCH = "llm decision player mismatch"
MESSAGE_MISSING_SPEECH_MESSAGE = "missing speech message"
MESSAGE_MISSING_VOTE_TARGET = "missing vote target"
MESSAGE_MISSING_ATTACK_TARGET = "missing attack target"
MESSAGE_MISSING_INSPECT_TARGET = "missing inspect target"
MESSAGE_MISSING_GUARD_TARGET = "missing guard target"
MESSAGE_EVENT_TYPE_MUST_NOT_BE_BLANK = "event_type must not be blank"
MESSAGE_DAY_MUST_BE_NON_NEGATIVE = "day must be zero or greater"
MESSAGE_PLAYER_COUNT_MUST_MATCH_PLAYERS = "player_count must match the number of players"
MESSAGE_PLAYER_COUNT_AT_LEAST_ONE = "player_count must be at least 1"
MESSAGE_ROLE_COUNTS_MUST_SUM_TO_PLAYER_COUNT = "role_counts must sum to player_count"
MESSAGE_ROLE_COUNTS_REQUIRE_WEREWOLF = "role_counts must include at least one werewolf-side player"
MESSAGE_ROLE_COUNTS_REQUIRE_VILLAGE_SIDE = (
    "role_counts must include at least one village-side player"
)
MESSAGE_SPEECH_ACTION_REQUIRES_MESSAGE = "message is required for speech actions"
MESSAGE_SPEECH_ACTION_FORBIDS_TARGET = "target_id is not allowed for speech actions"
MESSAGE_PASS_ACTION_FORBIDS_PAYLOAD = "pass actions cannot include target_id or message"
MESSAGE_SPEECH_DECISION_REQUIRES_MESSAGE = "message is required for speech decisions"
MESSAGE_SPEECH_DECISION_FORBIDS_TARGET = "target_id is not allowed for speech decisions"
MESSAGE_PASS_DECISION_FORBIDS_PAYLOAD = "pass decisions cannot include target_id or message"
MESSAGE_LOCAL_RULE_TIE_RULE_EXACTLY_ONE = (
    "exactly one tie rule must be enabled: "
    "enable_no_elimination_on_tie, enable_random_elimination_on_tie"
)
MESSAGE_GENERATED_PLAYER_INDEX_MUST_BE_AT_LEAST_ONE = "generated player index must be at least 1"
MESSAGE_CHARACTER_ASSIGNMENTS_KEYS_MUST_MATCH_PLAYERS = (
    "character_assignments keys must match generated player ids"
)
MESSAGE_CHARACTER_ASSIGNMENTS_VALUES_MUST_BE_UNIQUE = "character_assignments values must be unique"
MESSAGE_CUSTOM_ROLE_IDS_MUST_BE_UNIQUE = "custom role ids must be unique"
MESSAGE_CUSTOM_CHARACTER_IDS_MUST_BE_UNIQUE = "custom character ids must be unique"
MESSAGE_ROLE_ABILITIES_MUST_BE_UNIQUE = "role abilities must be unique"
MESSAGE_CUSTOM_ROLE_ABILITIES_MUST_BE_UNIQUE = "custom role abilities must be unique"
MESSAGE_CUSTOM_ROLES_CONFLICT_WITH_DEFAULT_ROLE_IDS = "custom roles conflict with default role ids"
MESSAGE_CUSTOM_ROLES_CONTAIN_UNKNOWN_ABILITIES = "custom roles contain unknown abilities"
MESSAGE_CUSTOM_CHARACTERS_CONFLICT_WITH_DEFAULT_CHARACTER_IDS = (
    "custom characters conflict with default character ids"
)
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
MESSAGE_AGENT_STRATEGIES_REQUIRED = "agent strategies must include at least one strategy"
MESSAGE_AGENT_STRATEGY_IDS_MUST_BE_UNIQUE = "agent strategy ids must be unique"
MESSAGE_AGENT_STRATEGY_DEFAULT_EXACTLY_ONE = (
    "agent strategies must mark exactly one default strategy"
)
MESSAGE_AGENT_STRATEGY_NODES_REQUIRED = "agent strategy nodes must include at least one node"
MESSAGE_AGENT_STRATEGY_NODES_MUST_BE_UNIQUE = "agent strategy nodes must be unique"
MESSAGE_DECISION_GRAPH_EDGES_REQUIRED = "decision graph edges must include at least one edge"
MESSAGE_DECISION_GRAPH_ROUTES_MUST_BE_UNIQUE = "decision graph routes must be unique"
MESSAGE_LLM_MODEL_NOT_CONFIGURED = "llm model is not configured"
MESSAGE_AGENT_PROFILES_REQUIRED = "profiles must include at least one enabled profile"
MESSAGE_LOG_FILE_NAME_MUST_BE_FILE_NAME = "log_file_name must be a file name"
MESSAGE_ROLE_COUNTS_MUST_BE_OBJECT = "role_counts must be an object"
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
MESSAGE_TELEMETRY_LEVEL_MUST_BE_VALID = (
    "telemetry level must be one of: DEBUG, INFO, WARNING, ERROR"
)
MESSAGE_SUPABASE_URL_MUST_START_WITH_HTTP = "supabase_url must start with http:// or https://"
MESSAGE_SUPABASE_CLIENT_SETTINGS_MUST_BE_PAIRED = (
    "WEREWOLF_SUPABASE_URL and WEREWOLF_SUPABASE_PUBLISHABLE_KEY must be set together."
)
MESSAGE_SUPABASE_WORKER_DSN_REQUIRED = "WEREWOLF_SUPABASE_DB_DSN is required for the worker."
MESSAGE_SUPABASE_AUTH_UNAVAILABLE = "Supabase Auth is unavailable."
MESSAGE_SUPABASE_AUTH_INVALID_RESPONSE = "Supabase Auth returned an invalid response."
MESSAGE_SUPABASE_AUTH_INCOMPLETE_SESSION = "Supabase Auth returned an incomplete session."
MESSAGE_SUPABASE_DATA_API_UNAVAILABLE = "Supabase Data API is unavailable."
MESSAGE_SUPABASE_DATA_API_NON_LIST_RESPONSE = "Supabase Data API returned a non-list response."
MESSAGE_SUPABASE_OPERATION_NOT_RETURNED = "Supabase did not return the queued operation."
MESSAGE_SUPABASE_GAME_REVEAL_NOT_FOUND = "Game reveal not found."
MESSAGE_ADVANCE_REQUEST_RESULT_MISSING = "Advance request completed without a result."
MESSAGE_ADVANCE_REQUEST_FAILED = "Advance request failed."
MESSAGE_ADVANCE_REQUEST_TIMED_OUT = "Advance request timed out."
MESSAGE_OPERATION_REQUEST_CANCELLED = "Operation request was cancelled."
MESSAGE_OPERATION_REQUEST_TIMED_OUT = "Operation request timed out."
MESSAGE_COMPLETED_OPERATION_RESULT_MISSING = (
    "Completed operation does not contain a result payload."
)
MESSAGE_OPERATION_REQUEST_FAILED = "Operation request failed."
MESSAGE_PLAYER_SEAT_NOT_OWNED = "The current user does not own this player seat."
MESSAGE_WORKER_REQUEST_FAILED = "Worker request failed."


def message_field_must_be_string(field_name: str) -> str:
    """Return a string-type validation message."""
    return f"{field_name} must be a string"


def message_field_must_not_be_blank(field_name: str) -> str:
    """Return a non-blank validation message."""
    return f"{field_name} must not be blank"


def message_field_must_be_one_of(field_name: str, choices: Iterable[str]) -> str:
    """Return a finite-choice validation message."""
    return f"{field_name} must be one of: {', '.join(sorted(choices))}"


def message_field_must_be_at_least(field_name: str, minimum: object) -> str:
    """Return a lower-bound validation message."""
    return f"{field_name} must be at least {minimum}"


def message_field_must_be_greater_than(field_name: str, minimum: object) -> str:
    """Return an exclusive lower-bound validation message."""
    return f"{field_name} must be greater than {minimum}"


def message_field_must_be_between(field_name: str, minimum: object, maximum: object) -> str:
    """Return an inclusive range validation message."""
    return f"{field_name} must be between {minimum} and {maximum}"


def message_field_must_not_exceed(field_name: str, maximum_field_name: str) -> str:
    """Return a field-pair ordering validation message."""
    return f"{field_name} must not exceed {maximum_field_name}"


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


def message_field_must_be_toml_table(field_name: str) -> str:
    """Return a TOML table validation message."""
    return f"{field_name} must be a TOML table"


def message_field_must_be_non_empty_string(field_name: str) -> str:
    """Return a non-empty string validation message."""
    return f"{field_name} must be a non-empty string"


def message_localized_keys_must_match_en(
    field_name: str,
    lang: str,
    *,
    missing: str,
    extra: str,
) -> str:
    """Return a localized message-key coverage validation message."""
    return f"{field_name}.{lang} keys must match en: missing={missing} extra={extra}"


def message_localized_label_kinds_must_match_en(lang: str) -> str:
    """Return a localized label-kind coverage validation message."""
    return f"labels.{lang} kinds must match en"


def message_streamlit_screen_definition_invalid(error: object) -> str:
    """Return a Streamlit screen-definition validation message."""
    return f"streamlit screen definition is invalid: {error}"


def message_streamlit_screen_unknown_region(screen_id: str, region_id: str) -> str:
    """Return an unknown Streamlit screen region message."""
    return f"streamlit screen {screen_id} has unknown region: {region_id}"


def message_streamlit_screen_unknown_element(
    screen_id: str,
    region_id: str,
    element_id: str,
) -> str:
    """Return an unknown Streamlit screen element message."""
    return f"streamlit screen {screen_id}.{region_id} has unknown element: {element_id}"


def message_streamlit_screen_duplicate_order(
    screen_id: str,
    region_id: str,
    order: int,
) -> str:
    """Return a duplicate Streamlit screen order message."""
    return f"streamlit screen {screen_id}.{region_id} has duplicate order: {order}"


def message_streamlit_screen_duplicate_element(
    screen_id: str,
    region_id: str,
    element_id: str,
    variant: str,
) -> str:
    """Return a duplicate Streamlit screen element message."""
    suffix = f":{variant}" if variant else ""
    return f"streamlit screen {screen_id}.{region_id} has duplicate element: {element_id}{suffix}"


def message_streamlit_screen_invalid_columns(screen_id: str) -> str:
    """Return an invalid Streamlit screen column-ratio message."""
    return f"streamlit screen {screen_id} column ratios must be positive"


def message_streamlit_screen_column_count_between(
    field_name: str,
    minimum: int,
    maximum: int,
) -> str:
    """Return a Streamlit screen column-count validation message."""
    return f"{field_name} must be between {minimum} and {maximum}"


def message_streamlit_screen_missing_layout(screen_id: str, field_name: str) -> str:
    """Return a missing Streamlit screen layout setting message."""
    return f"streamlit screen {screen_id} must define layout.{field_name}"


def message_definition_settings_invalid(error: object) -> str:
    """Return a runtime definition settings validation message."""
    return f"definition settings are invalid: {error}"


def message_role_definition_missing_player_counts(missing: str) -> str:
    """Return a role definition default-count coverage message."""
    return (
        f"game role definition default_role_counts must define configured player counts: {missing}"
    )


def message_role_count_must_be_zero_or_greater(role_id: str) -> str:
    """Return a role count validation message."""
    return f"role_counts[{role_id}] must be zero or greater"


def message_default_role_counts_unknown_roles(role_ids: Iterable[str]) -> str:
    """Return an unknown-role validation message for default role counts."""
    return f"default_role_counts contain unknown roles: {', '.join(role_ids)}"


def message_default_role_counts_must_sum(player_count: int) -> str:
    """Return a default role-count sum validation message."""
    return f"default_role_counts[{player_count}] must sum to {player_count}"


def message_default_role_counts_must_define_player_count(player_count: int) -> str:
    """Return a default role-count coverage validation message."""
    return f"default_role_counts must define player_count {player_count}"


def message_unknown_role_in_role_counts(role_id: str) -> str:
    """Return an unknown role-count key validation message."""
    return f"unknown role in role_counts: {role_id}"


def message_unsupported_faction(faction: str) -> str:
    """Return an unsupported faction validation message."""
    return f"unsupported faction: {faction}"


def message_unsupported_abilities(abilities: Iterable[str]) -> str:
    """Return an unsupported abilities validation message."""
    return f"unsupported abilities: {', '.join(abilities)}"


def message_target_required(action_type: str, subject: str) -> str:
    """Return a target-required validation message."""
    return f"target_id is required for {action_type} {subject}"


def message_message_not_allowed(action_type: str, subject: str) -> str:
    """Return a message-forbidden validation message."""
    return f"message is not allowed for {action_type} {subject}"


def message_unsupported_type(value: str, subject: str) -> str:
    """Return an unsupported-type validation message."""
    return f"unsupported {subject} type: {value}"


def message_unsupported_action_type(value: str) -> str:
    """Return an unsupported action type validation message."""
    return f"Unsupported action type: {value}"


def message_action_not_available(action_type: str, phase: str) -> str:
    """Return an action availability validation message."""
    return f"Action is not available now: {action_type} during {phase}."


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


def message_invalid_llm_decision(error_type: str) -> str:
    """Return an invalid LLM decision parse reason."""
    return f"invalid llm decision: {error_type}"


def message_llm_decision_action_unavailable(action_type: str) -> str:
    """Return an unavailable LLM decision action reason."""
    return f"llm decision action unavailable: {action_type}"


def message_llm_decision_target_unavailable(action_type: str) -> str:
    """Return an unavailable LLM decision target reason."""
    return f"llm decision target unavailable: {action_type}"


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


def message_unknown_setup_preset(preset_id: str) -> str:
    """Return an unknown setup preset message."""
    return f"Unknown setup preset: {preset_id}"


def message_unknown_scenario(scenario_id: str) -> str:
    """Return an unknown scenario message."""
    return f"Unknown scenario: {scenario_id}"


def message_llm_base_url_required(provider: str) -> str:
    """Return an LLM base URL requirement message."""
    return f"llm base_url is required for {provider} provider"


def message_openai_api_key_required(provider: str) -> str:
    """Return an OpenAI-compatible API key requirement message."""
    return f"OPENAI_API_KEY is required for {provider} provider"


def message_settings_llm_base_url_required(provider: str) -> str:
    """Return a settings-level LLM base URL requirement message."""
    return f"WEREWOLF_LLM_BASE_URL is required when WEREWOLF_LLM_PROVIDER={provider}"


def message_settings_openai_api_key_required(provider: str) -> str:
    """Return a settings-level OpenAI API key requirement message."""
    return f"OPENAI_API_KEY is required when WEREWOLF_LLM_PROVIDER={provider}"


def message_langchain_openai_required(*, lmstudio_provider: str, openai_provider: str) -> str:
    """Return a LangChain provider dependency message."""
    return (
        f"langchain-openai is required for {lmstudio_provider} and {openai_provider} LLM providers"
    )


def message_input_variables_not_used(names: str) -> str:
    """Return a prompt-template unused variable message."""
    return f"input_variables not used by messages: {names}"


def message_message_variables_missing(names: str) -> str:
    """Return a prompt-template missing variable message."""
    return f"message variables missing from input_variables: {names}"


def message_fake_decision_templates_required(action_type: str) -> str:
    """Return a FakeListLLM template coverage message."""
    return f"templates.{action_type} must include at least one item"


def message_decision_graph_node_unknown(node_id: str) -> str:
    """Return an unknown registered decision-graph node message."""
    return f"unknown decision graph node: {node_id}"


def message_decision_graph_endpoint_unknown(node_id: str) -> str:
    """Return an unknown decision-graph edge endpoint message."""
    return f"unknown decision graph endpoint: {node_id}"


def message_unknown_agent_strategy(strategy_id: str) -> str:
    """Return an unknown agent strategy message."""
    return f"Unknown agent strategy: {strategy_id}"


def message_game_did_not_complete(max_steps: int) -> str:
    """Return a CLI max-step failure message."""
    return f"Game did not complete within {max_steps} API steps."


def message_game_not_found(game_id: object) -> str:
    """Return an internal persistence missing-row message."""
    return MESSAGE_GAME_NOT_FOUND_TEMPLATE.format(game_id=game_id)


def message_api_unavailable(error: object) -> str:
    """Return an API connectivity failure message."""
    return f"api.unavailable: Could not connect to API ({error})."


def message_api_http_error(status_code: int) -> str:
    """Return an HTTP status failure message."""
    return f"api.http_error: API request failed with HTTP {status_code}."


def message_advance_job_timed_out(job_id: str) -> str:
    """Return an advance-job timeout message."""
    return f"api.unavailable: Advance job timed out: {job_id}."


def message_problem_detail(code: str, detail: str) -> str:
    """Return a CLI-safe Problem Details summary."""
    return f"{code}: {detail}"


def message_error_line(detail: str, suffix: str = "") -> str:
    """Return one CLI error line."""
    return f"Error: {detail}{suffix}"


def message_invalid_configuration_for(location: str, message: str) -> str:
    """Return a settings validation detail."""
    return f"Invalid configuration for {location}: {message}"


def message_unsupported_operation_type(operation_type: str) -> str:
    """Return an unsupported Supabase queue operation message."""
    return f"Unsupported operation_type: {operation_type}"


def message_supabase_auth_http_error(status_code: int) -> str:
    """Return a Supabase Auth HTTP failure message."""
    return f"Supabase Auth request failed with HTTP {status_code}."


def message_supabase_data_api_http_error(status_code: int) -> str:
    """Return a Supabase Data API HTTP failure message."""
    return f"Supabase Data API request failed with HTTP {status_code}."


def message_supabase_payload_schema_mismatch(model_name: str) -> str:
    """Return a Supabase payload schema mismatch message."""
    return f"Supabase payload does not match {model_name}."
