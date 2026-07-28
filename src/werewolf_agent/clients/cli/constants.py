"""clients cli constantsが所有する安定した値."""

from __future__ import annotations

from typing import Final, Literal, TypeAlias

MIN_PAGE_OFFSET: Final = 0

HEALTH_STATUS_OK: Final = "ok"

UNKNOWN_VALUE_LABEL: Final = "unknown"

MIN_INTERVAL_SECONDS: Final = 0

MIN_STEP_LIMIT: Final = 1

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

PYDANTIC_JSON_MODE: Final = "json"

JSON_SEPARATORS: Final[tuple[str, str]] = (",", ":")
