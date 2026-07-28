"""観測境界で使用する安定した値."""

from typing import Final, Literal, TypeAlias

EVENT_OUTCOME_SUCCESS: Final = "success"
EVENT_OUTCOME_FAILURE: Final = "failure"

__all__ = ["EVENT_OUTCOME_FAILURE", "EVENT_OUTCOME_SUCCESS"]


LOG_OUTPUT_FILE: Final = "file"

LOG_OUTPUT_STDERR: Final = "stderr"

LOG_OUTPUT_STDOUT: Final = "stdout"

LOG_OUTPUT_BOTH: Final = "both"

LOG_OUTPUT_NONE: Final = "none"

EVENT_VISIBILITY_DEBUG: Final = "debug"

EventVisibility: TypeAlias = Literal["public", "player_private", "debug"]

DEFAULT_ERROR_EVENT_VISIBILITY: Final[Literal["debug"]] = EVENT_VISIBILITY_DEBUG

ERROR_EVENT_TYPE: Final = "error_occurred"

JSON_ENCODING: Final = "utf-8"

JSONL_NEWLINE: Final = "\n"

JSON_SEPARATORS: Final[tuple[str, str]] = (",", ":")

FILE_MODE_APPEND: Final = "a"

FILE_MODE_WRITE: Final = "w"
