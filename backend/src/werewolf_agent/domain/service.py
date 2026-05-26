"""Public stateless services for the deterministic domain core."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence

from werewolf_agent.domain.models import (
    DomainEvent,
    GameConfig,
    GameSnapshot,
    NightAction,
    Observation,
    PlayerConfig,
    SpeechAction,
    VoteAction,
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
