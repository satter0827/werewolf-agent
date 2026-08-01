"""Phase-transition rules for the headless game."""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace

from werewolf_agent.domain._messages import message_cannot_advance_phase
from werewolf_agent.domain.errors import GamePhaseError
from werewolf_agent.domain.rule_packs import AbilityPolicy, VotingPolicy
from werewolf_agent.domain.rules.night_actions import resolve_night
from werewolf_agent.domain.rules.player_rules import check_win
from werewolf_agent.domain.rules.voting import resolve_votes
from werewolf_agent.domain.state import (
    Action,
    GameConfig,
    GameEvent,
    GameState,
    Phase,
    WinResult,
)


@dataclass(frozen=True)
class TransitionOutcome:
    """Internal result for one phase transition."""

    snapshot: GameState
    events: list[GameEvent] = field(default_factory=list)
    clear_votes: bool = False
    clear_night_actions: bool = False
    next_vote_round: int = 1
    revote_candidates: tuple[str, ...] = ()


def advance_game_phase(
    snapshot: GameState,
    config: GameConfig,
    pending_votes: Mapping[str, Action],
    pending_night_actions: Mapping[str, Action],
    rng: random.Random,
    *,
    vote_round: int = 1,
    ability_policy: AbilityPolicy,
    voting_policy: VotingPolicy,
    victory_evaluator: Callable[[GameState], WinResult | None] = check_win,
) -> TransitionOutcome:
    """Advance the state machine by one phase."""
    if snapshot.phase is Phase.NIGHT:
        return _advance_from_night(
            snapshot,
            config,
            pending_night_actions,
            rng,
            victory_evaluator,
            ability_policy=ability_policy,
        )
    if snapshot.phase is Phase.DAY_DISCUSSION:
        return _phase_only(snapshot, config)
    if snapshot.phase is Phase.VOTING:
        return _advance_from_voting(
            snapshot,
            config,
            pending_votes,
            rng,
            victory_evaluator,
            voting_policy=voting_policy,
            ability_policy=ability_policy,
            vote_round=vote_round,
        )
    raise GamePhaseError(
        message_cannot_advance_phase(snapshot.phase.value),
        context={"current_phase": snapshot.phase.value},
    )


def _advance_from_night(
    snapshot: GameState,
    config: GameConfig,
    pending_night_actions: Mapping[str, Action],
    rng: random.Random,
    victory_evaluator: Callable[[GameState], WinResult | None],
    *,
    ability_policy: AbilityPolicy,
) -> TransitionOutcome:
    resolved_snapshot, result = resolve_night(
        snapshot,
        pending_night_actions,
        rng,
        policy=ability_policy,
    )
    events = [
        GameEvent(
            event_type="night_resolved",
            phase=snapshot.phase,
            day=snapshot.day,
            payload={
                "killed_player_id": result.killed_player_id,
                "killed_player_ids": result.killed_player_ids,
                **_death_reveal(resolved_snapshot, result.killed_player_id),
            },
        )
    ]
    finished_snapshot, finish_events = _finish_or_move(
        resolved_snapshot,
        config,
        victory_evaluator,
    )
    return TransitionOutcome(
        snapshot=finished_snapshot,
        events=[*events, *finish_events],
        clear_night_actions=True,
    )


def _advance_from_voting(
    snapshot: GameState,
    config: GameConfig,
    pending_votes: Mapping[str, Action],
    rng: random.Random,
    victory_evaluator: Callable[[GameState], WinResult | None],
    *,
    ability_policy: AbilityPolicy,
    voting_policy: VotingPolicy,
    vote_round: int,
) -> TransitionOutcome:
    resolved_snapshot, result = resolve_votes(
        snapshot,
        pending_votes,
        rng,
        vote_round=vote_round,
        ability_policy=ability_policy,
        policy=voting_policy,
    )
    events = [
        GameEvent(
            event_type="vote_resolved",
            phase=snapshot.phase,
            day=snapshot.day,
            payload={
                "eliminated_player_id": result.eliminated_player_id,
                "counts": result.counts,
                "votes": result.votes,
                "reasons": result.reasons,
                "tied_player_ids": result.tied_player_ids,
                "round": result.round,
                "requires_revote": result.requires_revote,
                "reaction_player_ids": tuple(
                    player_id
                    for player_id, player in resolved_snapshot.players.items()
                    if not player.is_alive
                    and snapshot.players[player_id].is_alive
                    and player_id != result.eliminated_player_id
                ),
                **_death_reveal(resolved_snapshot, result.eliminated_player_id),
            },
        )
    ]
    if result.requires_revote:
        return TransitionOutcome(
            snapshot=resolved_snapshot,
            events=events,
            clear_votes=True,
            next_vote_round=2,
            revote_candidates=result.tied_player_ids,
        )
    if victory_evaluator(resolved_snapshot) is not None:
        finished_snapshot, finish_events = _finish_or_move(
            resolved_snapshot,
            config,
            victory_evaluator,
        )
    else:
        next_snapshot = _move_to_next(resolved_snapshot, config)
        finish_events = [_phase_started(next_snapshot)]
        finished_snapshot = next_snapshot
    return TransitionOutcome(
        snapshot=finished_snapshot,
        events=[*events, *finish_events],
        clear_votes=True,
        next_vote_round=1,
        revote_candidates=(),
    )


def _phase_only(snapshot: GameState, config: GameConfig) -> TransitionOutcome:
    next_snapshot = _move_to_next(snapshot, config)
    return TransitionOutcome(snapshot=next_snapshot, events=[_phase_started(next_snapshot)])


def _finish_or_move(
    snapshot: GameState,
    config: GameConfig,
    victory_evaluator: Callable[[GameState], WinResult | None],
) -> tuple[GameState, list[GameEvent]]:
    win_result = victory_evaluator(snapshot)
    if win_result is not None:
        finished = replace(snapshot, phase=Phase.FINISHED, win_result=win_result)
        return finished, [
            GameEvent(
                event_type="game_finished",
                phase=Phase.FINISHED,
                day=snapshot.day,
                payload={
                    "winner": win_result.winner,
                    "reason": win_result.reason,
                    "winning_player_ids": win_result.winning_player_ids,
                },
            )
        ]
    next_snapshot = _move_to_next(snapshot, config)
    return next_snapshot, [_phase_started(next_snapshot)]


def _phase_started(snapshot: GameState) -> GameEvent:
    return GameEvent(
        event_type="phase_started",
        phase=snapshot.phase,
        day=snapshot.day,
        payload={"phase": snapshot.phase.value},
    )


def _next_phase(config: GameConfig, current: Phase) -> Phase:
    index = config.phase_order.index(current)
    return config.phase_order[(index + 1) % len(config.phase_order)]


def _death_reveal(snapshot: GameState, player_id: str | None) -> dict[str, str]:
    if player_id is None or not snapshot.config.lifecycle.reveal_role_on_death:
        return {}
    player = snapshot.players[player_id]
    if player.role is None:
        return {}
    return {
        "role": player.role,
        "faction": snapshot.config.roles.faction_for_role(player.role),
    }


def _move_to_next(snapshot: GameState, config: GameConfig) -> GameState:
    next_phase = _next_phase(config, snapshot.phase)
    wrapped = config.phase_order.index(next_phase) <= config.phase_order.index(snapshot.phase)
    return replace(snapshot, phase=next_phase, day=snapshot.day + int(wrapped))
