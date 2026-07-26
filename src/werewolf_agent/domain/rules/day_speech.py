"""Day speech recording rules."""

from __future__ import annotations

from dataclasses import replace

from werewolf_agent.domain._messages import MESSAGE_EXPECTED_SPEECH_ACTION
from werewolf_agent.domain.errors import GameError
from werewolf_agent.domain.rules.player_rules import require_alive, require_phase
from werewolf_agent.domain.state import (
    Action,
    ActionType,
    GameEvent,
    GameState,
    Phase,
    SpeechRecord,
)


def record_day_speech(
    snapshot: GameState,
    action: Action,
) -> tuple[GameState, list[GameEvent]]:
    """Return an updated snapshot after recording one day speech."""
    require_phase(snapshot, Phase.DAY_DISCUSSION)
    require_alive(snapshot, action.player_id)
    if action.type is not ActionType.SPEECH or action.message is None:
        raise GameError(MESSAGE_EXPECTED_SPEECH_ACTION)

    speech = SpeechRecord(
        day=snapshot.day,
        player_id=action.player_id,
        message=action.message,
        reason=action.reason,
    )
    history = replace(snapshot.history, speeches=(*snapshot.history.speeches, speech))
    updated = replace(snapshot, history=history)
    return updated, [
        GameEvent(
            event_type="speech_recorded",
            phase=snapshot.phase,
            day=snapshot.day,
            actor_id=action.player_id,
            payload={"message": action.message},
        )
    ]
