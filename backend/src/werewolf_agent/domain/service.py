"""Public stateless services for the deterministic domain core."""

from __future__ import annotations

import random
from collections.abc import Sequence

from werewolf_agent.contracts import GameError
from werewolf_agent.domain.models import (
    Action,
    ActionType,
    DomainEvent,
    EventVisibility,
    GameConfig,
    GameSnapshot,
    Observation,
    PendingActions,
    Phase,
    Player,
    PlayerStatus,
    Role,
)
from werewolf_agent.domain.rules import (
    day_speech,
    game_setup,
    night_actions,
    observations,
    phase_transitions,
    voting,
)

_DEFAULT_SPEECH_TEMPLATES: tuple[str, ...] = (
    "I want to hear more from {target_name}.",
    "{target_name}'s vote history looks worth checking.",
    "I will compare today's claims before voting.",
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


def choose_dummy_action(
    player_id: str,
    observation: Observation,
    *,
    rng: random.Random,
    speech_templates: Sequence[str] = _DEFAULT_SPEECH_TEMPLATES,
) -> Action:
    """Return one deterministic dummy action from the player's visible observation."""
    if observation.me.id != player_id:
        return Action.pass_(
            player_id=player_id,
            reason="observation belongs to another player",
        )
    if observation.me.status is not PlayerStatus.ALIVE:
        return Action.pass_(player_id=player_id, reason="player is dead")
    if observation.phase is Phase.DAY_DISCUSSION:
        return _dummy_speech_action(player_id, observation, rng, speech_templates)
    if observation.phase is Phase.VOTING:
        return _dummy_vote_action(player_id, observation, rng)
    if observation.phase is Phase.NIGHT:
        return _dummy_night_action(player_id, observation, rng)
    return Action.pass_(
        player_id=player_id,
        reason=f"no action for {observation.phase.value}",
    )


def _dummy_speech_action(
    player_id: str,
    observation: Observation,
    rng: random.Random,
    speech_templates: Sequence[str],
) -> Action:
    candidates = _alive_candidate_ids(observation, include_self=False)
    target_id = _choose(candidates, rng)
    target_name = _name_for(observation, target_id) if target_id is not None else "everyone"
    template = rng.choice(tuple(speech_templates))
    return Action.speech(
        player_id=player_id,
        message=template.format(target_name=target_name),
    )


def _dummy_vote_action(
    player_id: str,
    observation: Observation,
    rng: random.Random,
) -> Action:
    candidates = _alive_candidate_ids(observation, include_self=False)
    target_id = _choose(candidates, rng)
    if target_id is None:
        return Action.pass_(player_id=player_id, reason="no valid vote targets")
    return Action.vote(
        player_id=player_id,
        target_id=target_id,
        reason="dummy seeded vote",
    )


def _dummy_night_action(
    player_id: str,
    observation: Observation,
    rng: random.Random,
) -> Action:
    role = observation.me.role
    if role is Role.WEREWOLF:
        return _dummy_werewolf_attack(player_id, observation, rng)
    if role is Role.SEER:
        return _dummy_seer_inspect(player_id, observation, rng)
    if role is Role.KNIGHT:
        return _dummy_knight_guard(player_id, observation, rng)
    return Action.pass_(player_id=player_id, reason="role has no night action")


def _dummy_werewolf_attack(
    player_id: str,
    observation: Observation,
    rng: random.Random,
) -> Action:
    candidates = [
        candidate_id
        for candidate_id in _alive_candidate_ids(observation, include_self=False)
        if observation.known_roles.get(candidate_id) is not Role.WEREWOLF
    ]
    target_id = _choose(candidates, rng)
    if target_id is None:
        return Action.pass_(player_id=player_id, reason="no attack targets")
    return Action.attack(
        player_id=player_id,
        target_id=target_id,
        reason="dummy seeded attack",
    )


def _dummy_seer_inspect(
    player_id: str,
    observation: Observation,
    rng: random.Random,
) -> Action:
    unknown_candidates = [
        candidate_id
        for candidate_id in _alive_candidate_ids(observation, include_self=False)
        if candidate_id not in observation.known_roles
    ]
    fallback_candidates = _alive_candidate_ids(observation, include_self=False)
    target_id = _choose(unknown_candidates or fallback_candidates, rng)
    if target_id is None:
        return Action.pass_(player_id=player_id, reason="no inspect targets")
    return Action.inspect(
        player_id=player_id,
        target_id=target_id,
        reason="dummy seeded inspection",
    )


def _dummy_knight_guard(
    player_id: str,
    observation: Observation,
    rng: random.Random,
) -> Action:
    candidates = _alive_candidate_ids(observation, include_self=True)
    target_id = _choose(candidates, rng)
    if target_id is None:
        return Action.pass_(player_id=player_id, reason="no guard targets")
    return Action.guard(
        player_id=player_id,
        target_id=target_id,
        reason="dummy seeded guard",
    )


def _alive_candidate_ids(observation: Observation, *, include_self: bool) -> list[str]:
    return [
        player.id
        for player in observation.players
        if player.status is PlayerStatus.ALIVE and (include_self or player.id != observation.me.id)
    ]


def _choose(candidates: Sequence[str], rng: random.Random) -> str | None:
    if not candidates:
        return None
    return rng.choice(sorted(candidates))


def _name_for(observation: Observation, player_id: str | None) -> str:
    if player_id is None:
        return "everyone"
    for player in observation.players:
        if player.id == player_id:
            return player.name
    return player_id


__all__ = [
    "advance_phase",
    "choose_dummy_action",
    "observe",
    "start_game",
    "submit_action",
]
