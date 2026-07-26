"""logging runtime settings section."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from werewolf_agent.settings.constants import (
    MIN_RETENTION_DAYS,
)
from werewolf_agent.settings.constants import (
    LogOutput as SharedLogOutput,
)


class LoggingSettings(BaseModel):
    """Settings owned by the logging runtime boundary."""

    log_level: str = Field(validation_alias="WEREWOLF_LOG_LEVEL")
    log_output: SharedLogOutput = Field(
        validation_alias="WEREWOLF_LOG_OUTPUT",
    )
    log_dir: Path = Field(validation_alias="WEREWOLF_LOG_DIR")
    log_file_name: str = Field(
        validation_alias="WEREWOLF_LOG_FILE_NAME",
    )
    log_retention_days: int = Field(
        ge=MIN_RETENTION_DAYS,
        validation_alias="WEREWOLF_LOG_RETENTION_DAYS",
    )
    log_third_party_level: str = Field(
        validation_alias="WEREWOLF_LOG_THIRD_PARTY_LEVEL",
    )
