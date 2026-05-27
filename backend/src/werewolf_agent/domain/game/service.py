"""Public stateless services for the deterministic domain core."""

from __future__ import annotations

import random
from collections.abc import Sequence

from werewolf_agent.contracts import GameError
from werewolf_agent.domain.game.models import (
    Action,
    ActionType,
    DomainEvent,
    EventVisibility,
    GameConfig,
    GameSnapshot,
    Observation,
    PendingActions,
    Player,
)
from werewolf_agent.domain.game.rules import (
    day_speech,
    game_setup,
    night_actions,
    observations,
    phase_transitions,
    voting,
)


def start_game(
    config: GameConfig,
    players: Sequence[Player],
    rng: random.Random,
) -> tuple[GameSnapshot, list[DomainEvent]]:
    """Create a validated initial game snapshot and startup events."""
    snapshot = game_setup.create_game_snapshot(config, players, rng)
    events = [
        DomainEvent(
            event_type="game_started",
            game_id=snapshot.game_id,
            phase=snapshot.phase,
            day=snapshot.day,
            payload={
                "player_count": config.player_count,
                "role_counts": {role.value: count for role, count in config.role_counts.items()},
            },
        )
    ]
    return snapshot, events


def observe(snapshot: GameSnapshot, player_id: str) -> Observation:
    """Return the information visible to one player."""
    return observations.build_player_observation(snapshot, player_id)


def submit_action(
    snapshot: GameSnapshot,
    pending_actions: PendingActions,
    action: Action,
) -> tuple[GameSnapshot, PendingActions, list[DomainEvent]]:
    """Validate and record one player action without advancing the phase."""
    if action.type is ActionType.SPEECH:
        next_snapshot, events = day_speech.record_day_speech(snapshot, action)
        return next_snapshot, pending_actions, events

    if action.type is ActionType.VOTE:
        votes = voting.record_vote(snapshot, snapshot.config, pending_actions.votes, action)
        return (
            snapshot,
            pending_actions.model_copy(update={"votes": votes}),
            [
                DomainEvent(
                    event_type="vote_submitted",
                    game_id=snapshot.game_id,
                    phase=snapshot.phase,
                    day=snapshot.day,
                    actor_id=action.player_id,
                    payload={"target_id": action.target_id},
                )
            ],
        )

    if action.is_night_action:
        actions = night_actions.record_night_action(
            snapshot,
            pending_actions.night_actions,
            action,
        )
        return (
            snapshot,
            pending_actions.model_copy(update={"night_actions": actions}),
            [
                DomainEvent(
                    event_type="night_action_submitted",
                    game_id=snapshot.game_id,
                    phase=snapshot.phase,
                    day=snapshot.day,
                    actor_id=action.player_id,
                    visibility=EventVisibility.PLAYER_PRIVATE,
                    payload={"action_type": action.type.value},
                )
            ],
        )

    if action.type is ActionType.PASS:
        return snapshot, pending_actions, []

    raise GameError("Unsupported agent action.")


def advance_phase(
    snapshot: GameSnapshot,
    pending_actions: PendingActions,
    rng: random.Random,
) -> tuple[GameSnapshot, PendingActions, list[DomainEvent]]:
    """Advance the state machine by one phase."""
    outcome = phase_transitions.advance_game_phase(
        snapshot,
        snapshot.config,
        pending_actions.votes,
        pending_actions.night_actions,
        rng,
    )
    updates: dict[str, object] = {}
    if outcome.clear_votes:
        updates["votes"] = {}
    if outcome.clear_night_actions:
        updates["night_actions"] = {}
    next_pending = pending_actions.model_copy(update=updates) if updates else pending_actions
    return outcome.snapshot, next_pending, outcome.events


__all__ = [
    "advance_phase",
    "observe",
    "start_game",
    "submit_action",
]
