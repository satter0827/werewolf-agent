"""Day speech recording rules."""

from __future__ import annotations

from werewolf_agent.commons.shared.messages import MESSAGE_EXPECTED_SPEECH_ACTION
from werewolf_agent.contracts import GameError
from werewolf_agent.domain.game.models import Action, ActionType, DomainEvent, GameSnapshot, Phase
from werewolf_agent.domain.game.rules.player_rules import require_alive, require_phase


def record_day_speech(
    snapshot: GameSnapshot,
    action: Action,
) -> tuple[GameSnapshot, list[DomainEvent]]:
    """Return an updated snapshot after recording one day speech."""
    require_phase(snapshot, Phase.DAY_DISCUSSION)
    require_alive(snapshot, action.player_id)
    if action.type is not ActionType.SPEECH or action.message is None:
        raise GameError(MESSAGE_EXPECTED_SPEECH_ACTION)

    history = snapshot.history.model_copy(update={"speeches": [*snapshot.history.speeches, action]})
    updated = snapshot.model_copy(update={"history": history})
    return updated, [
        DomainEvent(
            event_type="speech_recorded",
            game_id=snapshot.game_id,
            phase=snapshot.phase,
            day=snapshot.day,
            actor_id=action.player_id,
            payload={"message": action.message},
        )
    ]
