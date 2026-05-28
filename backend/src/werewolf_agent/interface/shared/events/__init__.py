"""Shared interface event factories and sinks."""

from werewolf_agent.interface.shared.events.factories import error_event
from werewolf_agent.interface.shared.events.sinks import EventSink, JsonlEventWriter, NullEventSink

__all__ = [
    "EventSink",
    "JsonlEventWriter",
    "NullEventSink",
    "error_event",
]
