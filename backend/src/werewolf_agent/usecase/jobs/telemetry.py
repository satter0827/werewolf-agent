"""Telemetry port for stateless use case jobs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, Literal, Protocol, cast

from werewolf_agent.commons.shared.validation import non_blank

TelemetryLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
TELEMETRY_LEVELS: Final = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


@dataclass(frozen=True)
class TelemetryEvent:
    """Structured diagnostic event emitted by use case workflows."""

    action: str
    fields: Mapping[str, object] = field(default_factory=dict)
    level: TelemetryLevel = "INFO"
    outcome: str | None = None

    def __post_init__(self) -> None:
        """Normalize event metadata without depending on interface logging."""
        object.__setattr__(self, "action", non_blank(self.action, "telemetry action"))
        level = str(self.level).upper()
        if level not in TELEMETRY_LEVELS:
            raise ValueError(
                "telemetry level must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL"
            )
        object.__setattr__(self, "level", cast(TelemetryLevel, level))
        object.__setattr__(self, "fields", dict(self.fields))
        if self.outcome is not None:
            object.__setattr__(self, "outcome", non_blank(self.outcome, "telemetry outcome"))


class TelemetrySink(Protocol):
    """Externally supplied diagnostic sink for use case workflows."""

    def record(self, event: TelemetryEvent) -> None:
        """Record one structured telemetry event."""


class NullTelemetrySink:
    """Telemetry sink used when no outer adapter is supplied."""

    def record(self, event: TelemetryEvent) -> None:
        """Drop one structured telemetry event."""
        _ = event
