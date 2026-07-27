"""application constantsが所有する安定した値."""

from __future__ import annotations

from typing import Final, Literal, TypeAlias

MIN_PAGE_LIMIT: Final = 1

MIN_PAGE_OFFSET: Final = 0

MIN_SEQUENCE: Final = 1

MIN_VERSION: Final = 1

NARRATION_MODE_NONE: Final = "none"

NARRATION_MODE_STANDARD: Final = "standard"

NARRATION_MODES: Final = (
    NARRATION_MODE_NONE,
    NARRATION_MODE_STANDARD,
)

NARRATION_MODE_CHOICES: Final = frozenset(NARRATION_MODES)

DEFAULT_NARRATION_MODE: Final[Literal["standard"]] = NARRATION_MODE_STANDARD

NarrationMode: TypeAlias = Literal["none", "standard"]

DELIBERATION_LEVEL_QUICK: Final = "quick"
DELIBERATION_LEVEL_STANDARD: Final = "standard"
DELIBERATION_LEVEL_DEEP: Final = "deep"
DELIBERATION_LEVELS: Final = (
    DELIBERATION_LEVEL_QUICK,
    DELIBERATION_LEVEL_STANDARD,
    DELIBERATION_LEVEL_DEEP,
)
DELIBERATION_LEVEL_CHOICES: Final = frozenset(DELIBERATION_LEVELS)
DEFAULT_DELIBERATION_LEVEL: Final[Literal["standard"]] = DELIBERATION_LEVEL_STANDARD

DeliberationLevel: TypeAlias = Literal["quick", "standard", "deep"]


MIN_ROLE_COUNT: Final = 0

MIN_PLAYER_COUNT: Final = 1

MIN_DIFFICULTY: Final = 1

MAX_DIFFICULTY: Final = 5

MIN_CHARACTER_AGE: Final = 18

MAX_CHARACTER_AGE: Final = 99

MIN_DAY_SPEECH_LIMIT_PER_PLAYER: Final = 1

MAX_DAY_SPEECH_LIMIT_PER_PLAYER: Final = 10
