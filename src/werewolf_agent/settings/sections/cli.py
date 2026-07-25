"""cli runtime settings section."""

from __future__ import annotations

from typing import cast

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
from werewolf_agent.settings.defaults import (
    DEFAULT_CLI_EVENT_LIMIT,
    DEFAULT_CLI_MAX_STEPS,
    DEFAULT_CLI_OUTPUT_FORMAT,
    DEFAULT_CLI_POLL_INTERVAL_SECONDS,
)


class CliSettings(BaseModel):
    """Settings owned by the cli runtime boundary."""

    cli_max_steps: int = Field(
        default=DEFAULT_CLI_MAX_STEPS,
        ge=MIN_STEP_LIMIT,
        validation_alias="WEREWOLF_CLI_MAX_STEPS",
    )
    cli_poll_interval_seconds: float = Field(
        default=DEFAULT_CLI_POLL_INTERVAL_SECONDS,
        ge=MIN_INTERVAL_SECONDS,
        validation_alias="WEREWOLF_CLI_POLL_INTERVAL_SECONDS",
    )
    cli_event_limit: int = Field(
        default=DEFAULT_CLI_EVENT_LIMIT,
        ge=MIN_PAGE_LIMIT,
        le=MAX_TIMELINE_LIMIT,
        validation_alias="WEREWOLF_CLI_EVENT_LIMIT",
    )
    cli_output_format: SharedCliOutputFormat = Field(
        default=cast(SharedCliOutputFormat, DEFAULT_CLI_OUTPUT_FORMAT),
        validation_alias="WEREWOLF_CLI_OUTPUT_FORMAT",
    )
