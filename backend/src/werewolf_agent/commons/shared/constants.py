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

MESSAGE_EVENT_TYPE_MUST_NOT_BE_BLANK: Final = "event_type must not be blank"
MESSAGE_DAY_MUST_BE_NON_NEGATIVE: Final = "day must be zero or greater"

JSON_ENCODING: Final = "utf-8"
JSONL_NEWLINE: Final = "\n"
JSON_SEPARATORS: Final[tuple[str, str]] = (",", ":")
FILE_MODE_APPEND: Final = "a"
FILE_MODE_WRITE: Final = "w"

LOG_CONTEXT_VAR_NAME: Final = "werewolf_log_context"
LOG_FORMAT_JSON: Final = "json"
LOG_FORMAT_CONSOLE: Final = "console"
LOG_OUTPUT_STDOUT: Final = "stdout"
LOG_STREAM_PREFIX: Final = "ext://sys."
LOG_HANDLER_DEFAULT: Final = "default"
ROOT_LOGGING_VERSION: Final = 1
DJANGO_LOGGER_NAME: Final = "django"
WEREWOLF_LOGGER_NAME: Final = "werewolf_agent"
DJANGO_LOGGING_KEY_VERSION: Final = "version"
DJANGO_LOGGING_KEY_DISABLE_EXISTING_LOGGERS: Final = "disable_existing_loggers"
DJANGO_LOGGING_KEY_FORMATTERS: Final = "formatters"
DJANGO_LOGGING_KEY_HANDLERS: Final = "handlers"
DJANGO_LOGGING_KEY_ROOT: Final = "root"
DJANGO_LOGGING_KEY_LOGGERS: Final = "loggers"
DJANGO_LOGGING_KEY_CLASS: Final = "class"
DJANGO_LOGGING_KEY_FORMATTER: Final = "formatter"
DJANGO_LOGGING_KEY_LEVEL: Final = "level"
DJANGO_LOGGING_KEY_STREAM: Final = "stream"
DJANGO_LOGGING_KEY_PROPAGATE: Final = "propagate"
DJANGO_LOGGING_KEY_FORMAT: Final = "format"
DJANGO_LOGGING_KEY_FACTORY: Final = "()"
LOGGING_STREAM_HANDLER_CLASS: Final = "logging.StreamHandler"
JSON_FORMATTER_DOTTED_PATH: Final = "werewolf_agent.commons.logging.formatters.JsonFormatter"
CONSOLE_LOG_FORMAT: Final = "%(levelname)s %(name)s: %(message)s"

LOG_FIELD_TIMESTAMP: Final = "timestamp"
LOG_FIELD_LEVEL: Final = "level"
LOG_FIELD_LOGGER: Final = "logger"
LOG_FIELD_MESSAGE: Final = "message"
LOG_FIELD_EXTRA: Final = "extra"
LOG_FIELD_EXCEPTION: Final = "exception"
LOG_FIELD_EXCEPTION_TYPE: Final = "type"
LOG_FIELD_EXCEPTION_STACKTRACE: Final = "stacktrace"
LOG_FIELD_EXCEPTION_MESSAGE: Final = "message"
STANDARD_LOG_MESSAGE_ATTRIBUTES: Final = frozenset({"message", "asctime"})
UTC_OFFSET_SUFFIX: Final = "+00:00"
UTC_ISO_SUFFIX: Final = "Z"
PRIVATE_ATTRIBUTE_PREFIX: Final = "_"
BASE_LOG_RECORD_NAME: Final = ""
BASE_LOG_RECORD_LEVEL: Final = 0
BASE_LOG_RECORD_PATHNAME: Final = ""
BASE_LOG_RECORD_LINENO: Final = 0
BASE_LOG_RECORD_MESSAGE: Final = ""
BASE_LOG_RECORD_ARGS: Final[tuple[()]] = ()
BASE_LOG_RECORD_EXC_INFO: Final = None

REDACTED: Final = "[REDACTED]"
REDACTION_SOURCE_SEPARATOR: Final = "-"
REDACTION_NORMALIZED_SEPARATOR: Final = "_"
SENSITIVE_KEY_PARTS: Final = (
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "password",
)
