"""Phase-transition rules for the headless game."""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace

from werewolf_agent.domain._messages import message_cannot_advance_phase
from werewolf_agent.domain.errors import GamePhaseError
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


def advance_game_phase(
    snapshot: GameState,
    config: GameConfig,
    pending_votes: Mapping[str, Action],
    pending_night_actions: Mapping[str, Action],
    rng: random.Random,
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
        )
    if snapshot.phase is Phase.DAY_DISCUSSION:
        return _phase_only(snapshot, config)
    if snapshot.phase is Phase.VOTING:
        return _advance_from_voting(snapshot, config, pending_votes, rng, victory_evaluator)
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
) -> TransitionOutcome:
    resolved_snapshot, result = resolve_night(snapshot, pending_night_actions, rng)
    events = [
        GameEvent(
            event_type="night_resolved",
            phase=snapshot.phase,
            day=snapshot.day,
            payload={
                "killed_player_id": result.killed_player_id,
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
) -> TransitionOutcome:
    resolved_snapshot, result = resolve_votes(snapshot, config, pending_votes, rng)
    events = [
        GameEvent(
            event_type="vote_resolved",
            phase=snapshot.phase,
            day=snapshot.day,
            payload={
                "eliminated_player_id": result.eliminated_player_id,
                "counts": result.counts,
                "tied_player_ids": result.tied_player_ids,
                **_death_reveal(resolved_snapshot, result.eliminated_player_id),
            },
        )
    ]
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
    if player_id is None or not snapshot.config.rules.reveal_role_on_death:
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
