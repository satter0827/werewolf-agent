"""Replay-oriented event factories and sinks."""

from werewolf_agent.observability.events.factories import error_event
from werewolf_agent.observability.events.sinks import EventSink, JsonlEventWriter, NullEventSink

__all__ = [
    "EventSink",
    "JsonlEventWriter",
    "NullEventSink",
    "error_event",
]
