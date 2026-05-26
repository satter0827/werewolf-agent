"""Day action handling."""

from __future__ import annotations

from werewolf_agent.domain._rules import require_alive, require_phase
from werewolf_agent.domain.models import DomainEvent, GameSnapshot, Phase, SpeechAction


def apply_day_action(
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
