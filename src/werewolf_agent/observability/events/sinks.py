"""Event sinks for replay-oriented game events."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from werewolf_agent.contracts.events import GameEvent
from werewolf_agent.observability.constants import (
    FILE_MODE_APPEND,
    FILE_MODE_WRITE,
    JSON_ENCODING,
    JSONL_NEWLINE,
)


class EventSink(Protocol):
    """Destination for game events."""

    def write(self, event: GameEvent) -> None:
        """Write one game event."""


class JsonlEventWriter:
    """Append game events to a newline-delimited JSON file."""

    def __init__(self, path: str | Path, *, append: bool = True) -> None:
        """Create a writer for one JSONL replay file."""
        self.path = Path(path)
        self._append = append
        self._has_written = False

    def write(self, event: GameEvent) -> None:
        """Write one event as one JSONL line."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        mode = FILE_MODE_APPEND if self._append or self._has_written else FILE_MODE_WRITE
        with self.path.open(mode, encoding=JSON_ENCODING, newline=JSONL_NEWLINE) as event_file:
            event_file.write(event.to_json_line())
            event_file.write(JSONL_NEWLINE)
        self._has_written = True


class NullEventSink:
    """Event sink used when replay logging is disabled."""

    def write(self, event: GameEvent) -> None:
        """Drop one game event."""
        _ = event
