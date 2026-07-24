"""Factories for replay-oriented game events."""

from __future__ import annotations

from werewolf_agent.configuration.constants import (
    DEFAULT_ERROR_EVENT_VISIBILITY,
    ERROR_EVENT_TYPE,
    EventVisibility,
)
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.events import GameEvent


def error_event(
    error: AppError,
    *,
    game_id: str | None = None,
    phase: str | None = None,
    day: int | None = None,
    actor_id: str | None = None,
    visibility: EventVisibility = DEFAULT_ERROR_EVENT_VISIBILITY,
) -> GameEvent:
    """Return a replay-safe event for an application error."""
    payload: dict[str, object] = {
        "code": error.code.value,
        "detail": error.detail,
        "retryable": error.retryable,
    }
    if error.context:
        payload["context"] = error.context

    return GameEvent(
        event_type=ERROR_EVENT_TYPE,
        game_id=game_id,
        phase=phase,
        day=day,
        actor_id=actor_id,
        visibility=visibility,
        payload=payload,
    )
