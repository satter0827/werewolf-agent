"""Telemetry adapters owned by API implementations."""

from __future__ import annotations

import logging
from typing import Final

from werewolf_agent.commons.shared.constants import EVENT_OUTCOME_SUCCESS
from werewolf_agent.usecase.jobs import TelemetryEvent

DEFAULT_TELEMETRY_LOGGER: Final = "werewolf_agent.usecase.telemetry"


class LoggingTelemetrySink:
    """Write use case telemetry events through process logging."""

    def __init__(self, logger_name: str = DEFAULT_TELEMETRY_LOGGER) -> None:
        """Create a sink that writes to the named process logger."""
        self._logger = logging.getLogger(logger_name)

    def record(self, event: TelemetryEvent) -> None:
        """Record one telemetry event as structured log data."""
        level = logging.getLevelName(event.level)
        level_number = level if isinstance(level, int) else logging.INFO
        extra = {
            **dict(event.fields),
            "event_action": event.action,
            "event_outcome": event.outcome or EVENT_OUTCOME_SUCCESS,
        }
        self._logger.log(level_number, event.action, extra=extra)
