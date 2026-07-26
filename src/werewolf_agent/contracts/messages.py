"""contracts messagesが所有する文言."""

from __future__ import annotations

TITLE_INVALID_CONFIGURATION = "Invalid Configuration"

TITLE_REQUEST_VALIDATION_FAILED = "Request Validation Failed"

TITLE_REQUEST_RATE_LIMITED = "Too Many Requests"

TITLE_REQUEST_BODY_TOO_LARGE = "Request Body Too Large"

TITLE_REQUEST_CONCURRENCY_LIMITED = "Request Capacity Exceeded"

TITLE_REQUEST_INVALID_CONTENT_LENGTH = "Invalid Content Length"

TITLE_REQUEST_TIMED_OUT = "Request Timed Out"

TITLE_IDEMPOTENCY_CONFLICT = "Idempotency Conflict"

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

TITLE_OPERATION_RETRY_EXHAUSTED = "Operation Retry Limit Exceeded"

TITLE_OPERATION_UPGRADE_INTERRUPTED = "Operation Interrupted by Upgrade"

TITLE_UNEXPECTED_INTERNAL_ERROR = "Unexpected Internal Error"

DETAIL_CONFIG_INVALID_VALUE = "The application configuration contains an invalid value."

DETAIL_REQUEST_VALIDATION_FAILED = "The request body or parameters failed validation."

DETAIL_REQUEST_RATE_LIMITED = "Wait briefly before trying the request again."

DETAIL_REQUEST_BODY_TOO_LARGE = "The request body exceeds the configured size limit."

DETAIL_REQUEST_CONCURRENCY_LIMITED = "The server is handling its maximum request capacity."

DETAIL_REQUEST_INVALID_CONTENT_LENGTH = "The Content-Length header is invalid."

DETAIL_REQUEST_TIMED_OUT = "The request did not finish within the configured timeout."

DETAIL_IDEMPOTENCY_CONFLICT = "The idempotency key was already used for another request."

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

DETAIL_OPERATION_RETRY_EXHAUSTED = "The operation failed after the configured retry limit."

DETAIL_OPERATION_UPGRADE_INTERRUPTED = "The queued operation must be submitted again."

DETAIL_INTERNAL_UNEXPECTED = "An unexpected internal error occurred."

MESSAGE_MANUAL_PLAYER_ID_MUST_MATCH_PLAYERS = "manual_player_id must match a generated player id."

MESSAGE_EVENT_TYPE_MUST_NOT_BE_BLANK = "event_type must not be blank"

MESSAGE_DAY_MUST_BE_NON_NEGATIVE = "day must be zero or greater"

MESSAGE_PLAYER_COUNT_AT_LEAST_ONE = "player_count must be at least 1"

MESSAGE_CHARACTER_ASSIGNMENTS_KEYS_MUST_MATCH_PLAYERS = (
    "character_assignments keys must match generated player ids"
)

MESSAGE_CHARACTER_ASSIGNMENTS_VALUES_MUST_BE_UNIQUE = "character_assignments values must be unique"

MESSAGE_CUSTOM_ROLE_IDS_MUST_BE_UNIQUE = "custom role ids must be unique"

MESSAGE_CUSTOM_CHARACTER_IDS_MUST_BE_UNIQUE = "custom character ids must be unique"


MESSAGE_LOCAL_RULE_TIE_RULE_EXACTLY_ONE = (
    "exactly one tie rule must be enabled: "
    "enable_no_elimination_on_tie, enable_random_elimination_on_tie"
)

MESSAGE_CUSTOM_ROLE_ABILITIES_MUST_BE_UNIQUE = "custom role abilities must be unique"
