"""Public stateless services for the deterministic domain core."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence

from werewolf_agent.domain.models import (
    AgentAction,
    DomainEvent,
    GameConfig,
    GameSnapshot,
    KnightGuardAction,
    NightAction,
    Observation,
    PassAction,
    Phase,
    PlayerConfig,
    PlayerStatus,
    Role,
    SeerInspectAction,
    SpeechAction,
    VoteAction,
    WerewolfAttackAction,
)
from werewolf_agent.domain.rules import (
    day_speech,
    game_setup,
    night_actions,
    observations,
    phase_transitions,
    voting,
)


def create_game_snapshot(
    config: GameConfig,
    players: Sequence[PlayerConfig],
    rng: random.Random,
) -> GameSnapshot:
    """Return a validated initial game snapshot."""
    return game_setup.create_game_snapshot(config, players, rng)


def build_player_observation(snapshot: GameSnapshot, player_id: str) -> Observation:
    """Return the information visible to one player."""
    return observations.build_player_observation(snapshot, player_id)


def decide_dummy_agent_action(
    player_id: str,
    observation: Observation,
    *,
    rng: random.Random,
    speech_templates: Sequence[str],
) -> AgentAction:
    """Return one deterministic dummy action from the player's visible observation."""
    if observation.player_id != player_id:
        return PassAction(
            player_id=player_id,
            reason="observation belongs to another player",
        )
    if observation.self_player.status is not PlayerStatus.ALIVE:
        return PassAction(player_id=player_id, reason="player is dead")
    if observation.phase is Phase.DAY_DISCUSSION:
        return _dummy_speech_action(player_id, observation, rng, speech_templates)
    if observation.phase is Phase.VOTING:
        return _dummy_vote_action(player_id, observation, rng)
    if observation.phase is Phase.NIGHT:
        return _dummy_night_action(player_id, observation, rng)
    return PassAction(
        player_id=player_id,
        reason=f"no action for {observation.phase.value}",
    )


def _dummy_speech_action(
    player_id: str,
    observation: Observation,
    rng: random.Random,
    speech_templates: Sequence[str],
) -> SpeechAction:
    candidates = _alive_candidate_ids(observation, include_self=False)
    target_id = _choose(candidates, rng)
    target_name = _name_for(observation, target_id) if target_id is not None else "everyone"
    template = rng.choice(tuple(speech_templates))
    return SpeechAction(
        player_id=player_id,
        message=template.format(target_name=target_name),
    )


def _dummy_vote_action(
    player_id: str,
    observation: Observation,
    rng: random.Random,
) -> AgentAction:
    candidates = _alive_candidate_ids(observation, include_self=False)
    target_id = _choose(candidates, rng)
    if target_id is None:
        return PassAction(player_id=player_id, reason="no valid vote targets")
    return VoteAction(
        player_id=player_id,
        target_id=target_id,
        reason="dummy seeded vote",
    )


def _dummy_night_action(
    player_id: str,
    observation: Observation,
    rng: random.Random,
) -> AgentAction:
    role = observation.self_player.role
    if role is Role.WEREWOLF:
        return _dummy_werewolf_attack(player_id, observation, rng)
    if role is Role.SEER:
        return _dummy_seer_inspect(player_id, observation, rng)
    if role is Role.KNIGHT:
        return _dummy_knight_guard(player_id, observation, rng)
    return PassAction(player_id=player_id, reason="role has no night action")


def _dummy_werewolf_attack(
    player_id: str,
    observation: Observation,
    rng: random.Random,
) -> AgentAction:
    candidates = [
        candidate_id
        for candidate_id in _alive_candidate_ids(observation, include_self=False)
        if observation.known_roles.get(candidate_id) is not Role.WEREWOLF
    ]
    target_id = _choose(candidates, rng)
    if target_id is None:
        return PassAction(player_id=player_id, reason="no attack targets")
    return WerewolfAttackAction(
        player_id=player_id,
        target_id=target_id,
        reason="dummy seeded attack",
    )


def _dummy_seer_inspect(
    player_id: str,
    observation: Observation,
    rng: random.Random,
) -> AgentAction:
    unknown_candidates = [
        candidate_id
        for candidate_id in _alive_candidate_ids(observation, include_self=False)
        if candidate_id not in observation.known_roles
    ]
    fallback_candidates = _alive_candidate_ids(observation, include_self=False)
    target_id = _choose(unknown_candidates or fallback_candidates, rng)
    if target_id is None:
        return PassAction(player_id=player_id, reason="no inspect targets")
    return SeerInspectAction(
        player_id=player_id,
        target_id=target_id,
        reason="dummy seeded inspection",
    )


def _dummy_knight_guard(
    player_id: str,
    observation: Observation,
    rng: random.Random,
) -> AgentAction:
    candidates = _alive_candidate_ids(observation, include_self=True)
    target_id = _choose(candidates, rng)
    if target_id is None:
        return PassAction(player_id=player_id, reason="no guard targets")
    return KnightGuardAction(
        player_id=player_id,
        target_id=target_id,
        reason="dummy seeded guard",
    )


def _alive_candidate_ids(observation: Observation, *, include_self: bool) -> list[str]:
    return [
        player.player_id
        for player in observation.players
        if player.status is PlayerStatus.ALIVE
        and (include_self or player.player_id != observation.player_id)
    ]


def _choose(candidates: Sequence[str], rng: random.Random) -> str | None:
    if not candidates:
        return None
    return rng.choice(sorted(candidates))


def _name_for(observation: Observation, player_id: str | None) -> str:
    if player_id is None:
        return "everyone"
    for player in observation.players:
        if player.player_id == player_id:
            return player.name
    return player_id


def record_day_speech(
    snapshot: GameSnapshot,
    action: SpeechAction,
) -> tuple[GameSnapshot, list[DomainEvent]]:
    """Return an updated snapshot after recording one day speech."""
    return day_speech.record_day_speech(snapshot, action)


def record_vote(
    snapshot: GameSnapshot,
    config: GameConfig,
    pending_votes: Mapping[str, VoteAction],
    action: VoteAction,
) -> dict[str, VoteAction]:
    """Validate and return pending votes with one vote recorded."""
    return voting.record_vote(snapshot, config, pending_votes, action)


def record_night_action(
    snapshot: GameSnapshot,
    pending_actions: Mapping[str, NightAction],
    action: NightAction,
) -> dict[str, NightAction]:
    """Validate and return pending night actions with one action recorded."""
    return night_actions.record_night_action(snapshot, pending_actions, action)


def advance_game_phase(
    snapshot: GameSnapshot,
    config: GameConfig,
    pending_votes: Mapping[str, VoteAction],
    pending_night_actions: Mapping[str, NightAction],
    rng: random.Random,
) -> tuple[GameSnapshot, list[DomainEvent], bool, bool]:
    """Advance the state machine by one phase."""
    outcome = phase_transitions.advance_game_phase(
        snapshot,
        config,
        pending_votes,
        pending_night_actions,
        rng,
    )
    return (
        outcome.snapshot,
        outcome.events,
        outcome.clear_votes,
        outcome.clear_night_actions,
    )
