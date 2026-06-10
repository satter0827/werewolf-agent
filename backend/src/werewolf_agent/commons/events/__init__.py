"""Shared event factories and sinks."""

from werewolf_agent.commons.events.factories import error_event
from werewolf_agent.commons.events.sinks import EventSink, JsonlEventWriter, NullEventSink

__all__ = [
    "EventSink",
    "JsonlEventWriter",
    "NullEventSink",
    "error_event",
]
