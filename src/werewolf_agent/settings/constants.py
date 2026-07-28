"""Runtime configuration constants."""

from __future__ import annotations

from typing import Final, Literal, TypeAlias

MIN_PAGE_LIMIT: Final = 1
MIN_PAGE_OFFSET: Final = 0
MAX_GAME_LIST_LIMIT: Final = 100
MAX_TIMELINE_LIMIT: Final = 500
MIN_SEQUENCE: Final = 1
MIN_VERSION: Final = 1
MIN_HTTP_STATUS_CODE: Final = 100
MAX_HTTP_STATUS_CODE: Final = 599
HTTP_FAILURE_STATUS_MIN: Final = 400
HTTP_SERVER_ERROR_STATUS_MIN: Final = 500
SECONDS_TO_MILLISECONDS: Final = 1000
DURATION_MILLISECONDS_DECIMAL_PLACES: Final = 3
EVENT_OUTCOME_SUCCESS: Final = "success"
EVENT_OUTCOME_FAILURE: Final = "failure"
HEALTH_STATUS_OK: Final = "ok"
UNKNOWN_VALUE_LABEL: Final = "unknown"
MIN_TIMEOUT_SECONDS_EXCLUSIVE: Final = 0
MIN_INTERVAL_SECONDS: Final = 0
MIN_INTERVAL_SECONDS_EXCLUSIVE: Final = 0
MIN_RETRY_COUNT: Final = 0
MIN_STEP_LIMIT: Final = 1
MIN_TEXT_MAX_CHARS: Final = 1
MIN_LLM_MAX_TOKENS: Final = 1

MIN_ROLE_COUNT: Final = 0
MIN_PLAYER_COUNT: Final = 1
MIN_DIFFICULTY: Final = 1
MAX_DIFFICULTY: Final = 5
MIN_CHARACTER_AGE: Final = 18
MAX_CHARACTER_AGE: Final = 99
MIN_DAY_SPEECH_LIMIT_PER_PLAYER: Final = 1
MAX_DAY_SPEECH_LIMIT_PER_PLAYER: Final = 10

NARRATION_MODE_NONE: Final = "none"
NARRATION_MODE_STANDARD: Final = "standard"
NARRATION_MODES: Final = (
    NARRATION_MODE_NONE,
    NARRATION_MODE_STANDARD,
)
NARRATION_MODE_CHOICES: Final = frozenset(NARRATION_MODES)
NarrationMode: TypeAlias = Literal["none", "standard"]

LLM_PROVIDER_FAKE: Final = "fake"
LLM_PROVIDER_LMSTUDIO: Final = "lmstudio"
LLM_PROVIDER_OPENAI: Final = "openai"
LLM_PROVIDER_CHOICES: Final = (
    LLM_PROVIDER_FAKE,
    LLM_PROVIDER_LMSTUDIO,
    LLM_PROVIDER_OPENAI,
)
LLM_PROVIDER_CHOICE_SET: Final = frozenset(LLM_PROVIDER_CHOICES)
LLM_MODEL_AUTO: Final = "auto"
LLM_STUDIO_API_KEY_PLACEHOLDER: Final = "lm-studio"
MIN_LLM_TEMPERATURE: Final = 0
MAX_LLM_TEMPERATURE: Final = 2
LlmProvider: TypeAlias = Literal["fake", "lmstudio", "openai"]

LOG_OUTPUT_FILE: Final = "file"
LOG_OUTPUT_STDERR: Final = "stderr"
LOG_OUTPUT_STDOUT: Final = "stdout"
LOG_OUTPUT_BOTH: Final = "both"
LOG_OUTPUT_NONE: Final = "none"
LOG_OUTPUT_CHOICES: Final = (
    LOG_OUTPUT_FILE,
    LOG_OUTPUT_STDERR,
    LOG_OUTPUT_STDOUT,
    LOG_OUTPUT_BOTH,
    LOG_OUTPUT_NONE,
)
LOG_OUTPUT_CHOICE_SET: Final = frozenset(LOG_OUTPUT_CHOICES)
LogOutput: TypeAlias = Literal["file", "stderr", "stdout", "both", "none"]

CLI_OUTPUT_FORMAT_TABLE: Final = "table"
CLI_OUTPUT_FORMAT_JSON: Final = "json"
CLI_OUTPUT_FORMAT_JSONL: Final = "jsonl"
CLI_OUTPUT_FORMAT_CHOICES: Final = (
    CLI_OUTPUT_FORMAT_TABLE,
    CLI_OUTPUT_FORMAT_JSON,
    CLI_OUTPUT_FORMAT_JSONL,
)
CLI_OUTPUT_FORMAT_CHOICE_SET: Final = frozenset(CLI_OUTPUT_FORMAT_CHOICES)
CliOutputFormat: TypeAlias = Literal["table", "json", "jsonl"]

EVENT_SCHEMA_VERSION: Final = "1.0"
EVENT_VISIBILITY_PUBLIC: Final = "public"
EVENT_VISIBILITY_PLAYER_PRIVATE: Final = "player_private"
EVENT_VISIBILITY_DEBUG: Final = "debug"
EventVisibility: TypeAlias = Literal["public", "player_private", "debug"]
ERROR_EVENT_TYPE: Final = "error_occurred"
GAME_EVENT_FIELD_EVENT_TYPE: Final = "event_type"
GAME_EVENT_FIELD_DAY: Final = "day"
MIN_EVENT_DAY: Final = 0
PYDANTIC_EXTRA_FORBID: Final = "forbid"
PYDANTIC_JSON_MODE: Final = "json"

JSON_ENCODING: Final = "utf-8"
JSONL_NEWLINE: Final = "\n"
JSON_SEPARATORS: Final[tuple[str, str]] = (",", ":")
FILE_MODE_APPEND: Final = "a"
FILE_MODE_WRITE: Final = "w"

REDACTED: Final = "[REDACTED]"
REDACTION_SOURCE_SEPARATOR: Final = "-"
REDACTION_NORMALIZED_SEPARATOR: Final = "_"
SENSITIVE_KEY_PARTS: Final = (
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "known_roles",
    "known_factions",
    "night_action",
    "password",
    "private_state",
    "raw_response",
    "role",
)
