"""logging runtime settings section."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, PrivateAttr

from werewolf_agent.settings.constants import (
    LogOutput as SharedLogOutput,
)
from werewolf_agent.settings.messages import MESSAGE_LOG_FILE_NAME_MUST_BE_FILE_NAME
from werewolf_agent.settings.validation import normalize_non_blank


class LoggingSettings(BaseModel):
    """Settings owned by the logging runtime boundary."""

    _log_file_name: str = PrivateAttr("werewolf-agent.jsonl")

    log_level: str = Field(validation_alias="WEREWOLF_LOG_LEVEL")
    log_output: SharedLogOutput = Field(
        validation_alias="WEREWOLF_LOG_OUTPUT",
    )
    log_dir: Path = Field(validation_alias="WEREWOLF_LOG_DIR")
    log_file_max_mib: int = Field(
        ge=1,
        validation_alias="WEREWOLF_LOG_FILE_MAX_MIB",
    )
    log_file_backup_count: int = Field(
        ge=1,
        validation_alias="WEREWOLF_LOG_FILE_BACKUP_COUNT",
    )
    log_third_party_level: str = Field(
        validation_alias="WEREWOLF_LOG_THIRD_PARTY_LEVEL",
    )

    @property
    def log_file_name(self) -> str:
        """Return the process-owned application log file name."""
        return self._log_file_name

    def with_log_file_name(self, file_name: str) -> Self:
        """Return a settings copy bound to one process-owned log file."""
        normalized = normalize_non_blank(file_name, field_name="log_file_name")
        if Path(normalized).name != normalized:
            raise ValueError(MESSAGE_LOG_FILE_NAME_MUST_BE_FILE_NAME)
        copied = self.model_copy()
        copied._log_file_name = normalized
        return copied
