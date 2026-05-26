"""Phase-transition rules for the headless game."""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass, field

from werewolf_agent.contracts import GamePhaseError
from werewolf_agent.domain.models import (
    Action,
    DomainEvent,
    EventVisibility,
    GameConfig,
    GameSnapshot,
    Phase,
)
from werewolf_agent.domain.rules.night_actions import resolve_night
from werewolf_agent.domain.rules.player_rules import check_win
from werewolf_agent.domain.rules.voting import resolve_votes


@dataclass(frozen=True)
class TransitionOutcome:
    """Internal result for one phase transition."""

    snapshot: GameSnapshot
    events: list[DomainEvent] = field(default_factory=list)
    clear_votes: bool = False
    clear_night_actions: bool = False


def advance_game_phase(
    snapshot: GameSnapshot,
    config: GameConfig,
    pending_votes: Mapping[str, Action],
    pending_night_actions: Mapping[str, Action],
    rng: random.Random,
) -> TransitionOutcome:
    """Advance the state machine by one phase."""
    if snapshot.phase is Phase.NIGHT:
        return _advance_from_night(snapshot, pending_night_actions, rng)
    if snapshot.phase is Phase.DAY_DISCUSSION:
        return _phase_only(snapshot, Phase.VOTING)
    if snapshot.phase is Phase.VOTING:
        return _advance_from_voting(snapshot, config, pending_votes, rng)
    raise GamePhaseError(
        f"Cannot advance phase from {snapshot.phase.value}.",
        context={"current_phase": snapshot.phase.value},
    )


def _advance_from_night(
    snapshot: GameSnapshot,
    pending_night_actions: Mapping[str, Action],
    rng: random.Random,
) -> TransitionOutcome:
    resolved_snapshot, result = resolve_night(snapshot, pending_night_actions, rng)
    events = [
        DomainEvent(
            event_type="night_resolved",
            game_id=snapshot.game_id,
            phase=snapshot.phase,
            day=snapshot.day,
            visibility=EventVisibility.DEBUG,
            payload={
                "attacked_player_id": result.attacked_player_id,
                "protected_player_id": result.protected_player_id,
                "killed_player_id": result.killed_player_id,
            },
        )
    ]
    finished_snapshot, finish_events = _finish_or_move(resolved_snapshot, Phase.DAY_DISCUSSION)
    return TransitionOutcome(
        snapshot=finished_snapshot,
        events=[*events, *finish_events],
        clear_night_actions=True,
    )


def _advance_from_voting(
    snapshot: GameSnapshot,
    config: GameConfig,
    pending_votes: Mapping[str, Action],
    rng: random.Random,
) -> TransitionOutcome:
    resolved_snapshot, result = resolve_votes(snapshot, config, pending_votes, rng)
    events = [
        DomainEvent(
            event_type="vote_resolved",
            game_id=snapshot.game_id,
            phase=snapshot.phase,
            day=snapshot.day,
            payload={
                "eliminated_player_id": result.eliminated_player_id,
                "counts": result.counts,
                "tied_player_ids": result.tied_player_ids,
            },
        )
    ]
    if check_win(resolved_snapshot) is not None:
        finished_snapshot, finish_events = _finish_or_move(resolved_snapshot, Phase.NIGHT)
    else:
        next_snapshot = resolved_snapshot.model_copy(
            update={"phase": Phase.NIGHT, "day": snapshot.day + 1}
        )
        finish_events = [_phase_started(next_snapshot)]
        finished_snapshot = next_snapshot
    return TransitionOutcome(
        snapshot=finished_snapshot,
        events=[*events, *finish_events],
        clear_votes=True,
    )


def _phase_only(snapshot: GameSnapshot, phase: Phase) -> TransitionOutcome:
    next_snapshot = snapshot.model_copy(update={"phase": phase})
    return TransitionOutcome(snapshot=next_snapshot, events=[_phase_started(next_snapshot)])


def _finish_or_move(
    snapshot: GameSnapshot,
    next_phase: Phase,
) -> tuple[GameSnapshot, list[DomainEvent]]:
    win_result = check_win(snapshot)
    if win_result is not None:
        finished = snapshot.model_copy(update={"phase": Phase.FINISHED, "win_result": win_result})
        return finished, [
            DomainEvent(
                event_type="game_finished",
                game_id=snapshot.game_id,
                phase=Phase.FINISHED,
                day=snapshot.day,
                payload={
                    "winner": win_result.winner.value,
                    "reason": win_result.reason,
                    "winning_player_ids": win_result.winning_player_ids,
                },
            )
        ]
    next_snapshot = snapshot.model_copy(update={"phase": next_phase})
    return next_snapshot, [_phase_started(next_snapshot)]


def _phase_started(snapshot: GameSnapshot) -> DomainEvent:
    return DomainEvent(
        event_type="phase_started",
        game_id=snapshot.game_id,
        phase=snapshot.phase,
        day=snapshot.day,
        payload={"phase": snapshot.phase.value},
    )
