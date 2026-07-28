"""clients streamlit constantsが所有する安定した値."""

from __future__ import annotations

from typing import Final, Literal

UNKNOWN_VALUE_LABEL: Final = "unknown"

NARRATION_MODE_NONE: Final = "none"

NARRATION_MODE_STANDARD: Final = "standard"

DEFAULT_NARRATION_MODE: Final[Literal["standard"]] = NARRATION_MODE_STANDARD

SETUP_DRAFT_KEY: Final = "werewolf_setup_document_draft_v2"
