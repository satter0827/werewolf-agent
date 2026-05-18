"""Game event records and JSONL sinks for replay-oriented logs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from pydantic.functional_validators import field_validator

from werewolf_agent.commons import AppError
from werewolf_agent.commons.schemas import ErrorEventPayload
from werewolf_agent.observation.redaction import redact_mapping

EventVisibility = Literal["public", "player_private", "debug"]


class GameEvent(BaseModel):
    """A replay-oriented game event written independently from application logs."""

    schema_version: str = "1.0"
    event_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: str
    run_id: str | None = None
    game_id: str | None = None
    phase: str | None = None
    day: int | None = None
    actor_id: str | None = None
    visibility: EventVisibility = "public"
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        """Return a non-empty event type."""
        normalized = value.strip()
        if not normalized:
            msg = "event_type must not be blank"
            raise ValueError(msg)
        return normalized

    @field_validator("day")
    @classmethod
    def validate_day(cls, value: int | None) -> int | None:
        """Return a non-negative day value."""
        if value is not None and value < 0:
            msg = "day must be zero or greater"
            raise ValueError(msg)
        return value

    def to_json_line(self) -> str:
        """Return this event as a single JSON object string."""
        event_record = redact_mapping(self.model_dump(mode="json"))
        return json.dumps(
            event_record,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        )


def error_event(
    error: AppError,
    *,
    run_id: str | None = None,
    game_id: str | None = None,
    phase: str | None = None,
    day: int | None = None,
    actor_id: str | None = None,
    visibility: EventVisibility = "debug",
) -> GameEvent:
    """Return a replay-safe event for an application error."""
    payload = ErrorEventPayload(
        code=error.code.value,
        detail=error.detail,
        retryable=error.retryable,
        context=error.context or None,
    ).model_dump(mode="json", exclude_none=True)

    return GameEvent(
        event_type="error_occurred",
        run_id=run_id,
        game_id=game_id,
        phase=phase,
        day=day,
        actor_id=actor_id,
        visibility=visibility,
        payload=payload,
    )


class EventSink(Protocol):
    """Destination for game events."""

    def write(self, event: GameEvent) -> None:
        """Write one game event."""


class JsonlEventWriter:
    """Append game events to a newline-delimited JSON file."""

    def __init__(self, path: str | Path, *, append: bool = True) -> None:
        self.path = Path(path)
        self._append = append
        self._has_written = False

    def write(self, event: GameEvent) -> None:
        """Write one event as one JSONL line."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if self._append or self._has_written else "w"
        with self.path.open(mode, encoding="utf-8", newline="\n") as event_file:
            event_file.write(event.to_json_line())
            event_file.write("\n")
        self._has_written = True


class NullEventSink:
    """Event sink used when replay logging is disabled."""

    def write(self, event: GameEvent) -> None:
        """Drop one game event."""
        _ = event
