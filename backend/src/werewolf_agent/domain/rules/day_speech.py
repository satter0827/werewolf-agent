"""Day speech recording rules."""

from __future__ import annotations

from werewolf_agent.domain.models import DomainEvent, GameSnapshot, Phase, SpeechAction
from werewolf_agent.domain.rules.player_rules import require_alive, require_phase


def record_day_speech(
    snapshot: GameSnapshot,
    action: SpeechAction,
) -> tuple[GameSnapshot, list[DomainEvent]]:
    """Return an updated snapshot after recording one day speech."""
    require_phase(snapshot, Phase.DAY_DISCUSSION)
    require_alive(snapshot, action.player_id)

    speeches = [*snapshot.speeches, action]
    updated = snapshot.model_copy(update={"speeches": speeches})
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
