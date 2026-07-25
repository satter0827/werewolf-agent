"""contracts constantsが所有する安定した値."""

from __future__ import annotations

from typing import Final, Literal, TypeAlias

MIN_PAGE_LIMIT: Final = 1

MIN_PAGE_OFFSET: Final = 0

MIN_SEQUENCE: Final = 1

MIN_VERSION: Final = 1

MIN_HTTP_STATUS_CODE: Final = 100

MAX_HTTP_STATUS_CODE: Final = 599

MIN_ROLE_COUNT: Final = 0

MIN_DIFFICULTY: Final = 1

MAX_DIFFICULTY: Final = 5

MIN_CHARACTER_AGE: Final = 18

MAX_CHARACTER_AGE: Final = 99

NARRATION_MODE_STANDARD: Final = "standard"

DEFAULT_NARRATION_MODE: Final[Literal["standard"]] = NARRATION_MODE_STANDARD

NarrationMode: TypeAlias = Literal["none", "standard", "rich"]

EVENT_SCHEMA_VERSION: Final = "1.0"

EVENT_VISIBILITY_PUBLIC: Final = "public"

EventVisibility: TypeAlias = Literal["public", "player_private", "debug"]

DEFAULT_EVENT_VISIBILITY: Final[Literal["public"]] = EVENT_VISIBILITY_PUBLIC

GAME_EVENT_FIELD_EVENT_TYPE: Final = "event_type"

GAME_EVENT_FIELD_DAY: Final = "day"

MIN_EVENT_DAY: Final = 0

PYDANTIC_EXTRA_FORBID: Final = "forbid"

PYDANTIC_JSON_MODE: Final = "json"

JSON_SEPARATORS: Final[tuple[str, str]] = (",", ":")


MIN_DAY_SPEECH_LIMIT_PER_PLAYER: Final = 1

MAX_DAY_SPEECH_LIMIT_PER_PLAYER: Final = 10

GENERATED_PLAYER_ID_PREFIX: Final = "player"

GENERATED_PLAYER_ID_SEPARATOR: Final = "-"

GENERATED_PLAYER_NAME_PREFIX: Final = "Player"

GENERATED_PLAYER_NAME_SEPARATOR: Final = " "

GENERATED_PLAYER_NUMBER_START: Final = 1

PUBLIC_PLAYER_LABEL_PREFIX: Final = "P"
