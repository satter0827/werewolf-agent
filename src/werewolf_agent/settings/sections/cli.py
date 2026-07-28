"""cli runtime settings section."""

from __future__ import annotations

from pydantic import BaseModel, Field

from werewolf_agent.settings.constants import (
    MAX_TIMELINE_LIMIT,
    MIN_INTERVAL_SECONDS,
    MIN_PAGE_LIMIT,
    MIN_STEP_LIMIT,
)
from werewolf_agent.settings.constants import (
    CliOutputFormat as SharedCliOutputFormat,
)


class CliSettings(BaseModel):
    """Settings owned by the cli runtime boundary."""

    cli_max_steps: int = Field(
        ge=MIN_STEP_LIMIT,
        validation_alias="WEREWOLF_CLI_MAX_STEPS",
    )
    cli_poll_interval_seconds: float = Field(
        ge=MIN_INTERVAL_SECONDS,
        validation_alias="WEREWOLF_CLI_POLL_INTERVAL_SECONDS",
    )
    cli_event_limit: int = Field(
        ge=MIN_PAGE_LIMIT,
        le=MAX_TIMELINE_LIMIT,
        validation_alias="WEREWOLF_CLI_EVENT_LIMIT",
    )
    cli_output_format: SharedCliOutputFormat = Field(
        validation_alias="WEREWOLF_CLI_OUTPUT_FORMAT",
    )
