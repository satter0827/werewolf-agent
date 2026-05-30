"""Constants shared by commons helpers."""

from __future__ import annotations

from typing import Final, Literal, TypeAlias

EVENT_SCHEMA_VERSION: Final = "1.0"
EVENT_VISIBILITY_PUBLIC: Final = "public"
EVENT_VISIBILITY_PLAYER_PRIVATE: Final = "player_private"
EVENT_VISIBILITY_DEBUG: Final = "debug"
EventVisibility: TypeAlias = Literal["public", "player_private", "debug"]
DEFAULT_EVENT_VISIBILITY: Final[Literal["public"]] = EVENT_VISIBILITY_PUBLIC
DEFAULT_ERROR_EVENT_VISIBILITY: Final[Literal["debug"]] = EVENT_VISIBILITY_DEBUG
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
    "night_action",
    "password",
    "private_state",
    "raw_response",
    "role",
)
