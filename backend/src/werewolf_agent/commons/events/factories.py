"""Factories for replay-oriented game events."""

from __future__ import annotations

from werewolf_agent.commons.events.models import GameEvent
from werewolf_agent.commons.shared.constants import (
    DEFAULT_ERROR_EVENT_VISIBILITY,
    ERROR_EVENT_TYPE,
    EventVisibility,
)
from werewolf_agent.contracts import AppError


def error_event(
    error: AppError,
    *,
    run_id: str | None = None,
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
        run_id=run_id,
        game_id=game_id,
        phase=phase,
        day=day,
        actor_id=actor_id,
        visibility=visibility,
        payload=payload,
    )
