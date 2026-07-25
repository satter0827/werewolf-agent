"""logging runtime settings section."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from pydantic import BaseModel, Field

from werewolf_agent.settings.constants import (
    MIN_RETENTION_DAYS,
)
from werewolf_agent.settings.constants import (
    LogOutput as SharedLogOutput,
)
from werewolf_agent.settings.defaults import (
    DEFAULT_LOG_DIR,
    DEFAULT_LOG_FILE_NAME,
    DEFAULT_LOG_LEVEL,
    DEFAULT_LOG_OUTPUT,
    DEFAULT_LOG_RETENTION_DAYS,
    DEFAULT_LOG_THIRD_PARTY_LEVEL,
)


class LoggingSettings(BaseModel):
    """Settings owned by the logging runtime boundary."""

    log_level: str = Field(default=DEFAULT_LOG_LEVEL, validation_alias="WEREWOLF_LOG_LEVEL")
    log_output: SharedLogOutput = Field(
        default=cast(SharedLogOutput, DEFAULT_LOG_OUTPUT),
        validation_alias="WEREWOLF_LOG_OUTPUT",
    )
    log_dir: Path = Field(default=DEFAULT_LOG_DIR, validation_alias="WEREWOLF_LOG_DIR")
    log_file_name: str = Field(
        default=DEFAULT_LOG_FILE_NAME,
        validation_alias="WEREWOLF_LOG_FILE_NAME",
    )
    log_retention_days: int = Field(
        default=DEFAULT_LOG_RETENTION_DAYS,
        ge=MIN_RETENTION_DAYS,
        validation_alias="WEREWOLF_LOG_RETENTION_DAYS",
    )
    log_third_party_level: str = Field(
        default=DEFAULT_LOG_THIRD_PARTY_LEVEL,
        validation_alias="WEREWOLF_LOG_THIRD_PARTY_LEVEL",
    )
