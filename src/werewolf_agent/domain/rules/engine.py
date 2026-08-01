"""Concrete deterministic rule pipeline owned by the domain aggregate."""

from __future__ import annotations

import random
from dataclasses import replace

from werewolf_agent.domain._messages import MESSAGE_UNSUPPORTED_AGENT_ACTION
from werewolf_agent.domain.errors import GameError, RuleViolation
from werewolf_agent.domain.rule_packs import (
    AbilityPolicy,
    DiscussionPolicy,
    VictoryPolicy,
    VotingPolicy,
)
from werewolf_agent.domain.rules import (
    action_availability,
    discussion,
    night_actions,
    observations,
    phase_transitions,
    voting,
)
from werewolf_agent.domain.state import (
    Action,
    ActionType,
    EventVisibility,
    GameEvent,
    GameState,
    GameView,
    PendingActions,
    Phase,
    WinResult,
)


def validate_action(state: GameState, pending: PendingActions, action: Action) -> None:
    """Reject an action outside the configured legal-action set."""
    try:
        action_availability.require_action_available(state, pending, action)
    except GameError as exc:
        raise RuleViolation("action_not_available", str(exc)) from exc


def resolve_action(
    state: GameState,
    pending: PendingActions,
    action: Action,
) -> tuple[GameState, PendingActions, list[GameEvent]]:
    """Resolve one accepted action through the only supported pipeline."""
    if state.phase is Phase.DAY_DISCUSSION and action.type in {
        ActionType.SPEECH,
        ActionType.PASS,
    }:
        round_ = pending.discussion_round
        if round_ is None:
            raise RuleViolation("discussion_not_started", "Discussion round is not initialized.")
        actions = discussion.record_discussion_submission(
            state,
            round_,
            pending.discussion_actions,
            action,
        )
        return (
            state,
            replace(pending, discussion_actions=actions),
            [_private_submission_event(state, action, "discussion_action_submitted")],
        )
    if action.type is ActionType.VOTE:
        votes = voting.record_vote(
            state,
            state.config,
            pending.votes,
            action,
            candidates=pending.revote_candidates,
        )
        return (
            state,
            replace(pending, votes=votes),
            [_private_submission_event(state, action, "vote_submitted")],
        )
    if state.phase is Phase.NIGHT and action.type in {ActionType.USE_ABILITY, ActionType.PASS}:
        actions = night_actions.record_night_action(state, pending.night_actions, action)
        return (
            state,
            replace(pending, night_actions=actions),
            [_private_submission_event(state, action, "night_action_submitted")],
        )
    raise GameError(MESSAGE_UNSUPPORTED_AGENT_ACTION)


def validate_phase_advance(state: GameState, pending: PendingActions) -> None:
    """Reject phase advancement while configured required actions remain."""
    if not state.config.lifecycle.require_all_actions_before_advance:
        return
    if state.phase not in {Phase.NIGHT, Phase.DAY_DISCUSSION, Phase.VOTING}:
        return
    missing = [
        player.id
        for player in state.players.values()
        if player.is_alive and action_availability.available_actions(state, pending, player.id)
    ]
    if missing:
        raise RuleViolation(
            "required_actions_missing",
            "Required actions are missing.",
            context={"phase": state.phase.value, "player_ids": tuple(sorted(missing))},
        )


def advance_phase(
    state: GameState,
    pending: PendingActions,
    random_source: random.Random,
    *,
    ability_policy: AbilityPolicy,
    discussion_policy: DiscussionPolicy,
    voting_policy: VotingPolicy,
    victory_policy: VictoryPolicy,
) -> tuple[GameState, PendingActions, list[GameEvent]]:
    """Advance one phase and evaluate the fixed faction victory boundary."""
    if state.phase is Phase.DAY_DISCUSSION:
        round_ = pending.discussion_round
        if round_ is None:
            raise RuleViolation("discussion_not_started", "Discussion round is not initialized.")
        next_state, resolution, events = discussion.resolve_discussion_round(
            state,
            round_,
            pending.discussion_actions,
            policy=discussion_policy,
        )
        next_pending = replace(
            pending,
            discussion_actions={},
            discussion_round=resolution.next_round,
        )
        if not resolution.completed:
            return next_state, next_pending, events
        next_state = replace(next_state, pending_actions=next_pending)
        outcome = phase_transitions.advance_game_phase(
            next_state,
            next_state.config,
            next_pending.votes,
            next_pending.night_actions,
            random_source,
            vote_round=next_pending.vote_round,
            ability_policy=ability_policy,
            voting_policy=voting_policy,
            victory_evaluator=lambda _state: None,
        )
        next_state = outcome.snapshot
        next_pending = replace(next_pending, discussion_round=None, discussion_actions={})
        events = [*events, *outcome.events]
        win_result = victory_policy.evaluate(next_state)
        if win_result is not None:
            next_state = replace(next_state, phase=Phase.FINISHED, win_result=win_result)
            events.append(_game_finished_event(next_state, win_result))
        return next_state, next_pending, events

    outcome = phase_transitions.advance_game_phase(
        state,
        state.config,
        pending.votes,
        pending.night_actions,
        random_source,
        vote_round=pending.vote_round,
        ability_policy=ability_policy,
        voting_policy=voting_policy,
        victory_evaluator=lambda _state: None,
    )
    next_pending = replace(
        pending,
        votes={} if outcome.clear_votes else pending.votes,
        night_actions={} if outcome.clear_night_actions else pending.night_actions,
        vote_round=outcome.next_vote_round,
        revote_candidates=outcome.revote_candidates,
    )
    next_state = outcome.snapshot
    if next_state.phase is Phase.DAY_DISCUSSION:
        next_pending = replace(
            next_pending,
            discussion_round=discussion_policy.start(next_state),
            discussion_actions={},
        )
    else:
        next_pending = replace(
            next_pending,
            discussion_round=None,
            discussion_actions={},
        )
    events = outcome.events
    win_result = victory_policy.evaluate(next_state)
    if win_result is not None:
        next_state = replace(next_state, phase=Phase.FINISHED, win_result=win_result)
        next_pending = replace(
            next_pending,
            discussion_round=None,
            discussion_actions={},
        )
        events = [*events, _game_finished_event(next_state, win_result)]
    return next_state, next_pending, events


def _game_finished_event(state: GameState, win_result: WinResult) -> GameEvent:
    return GameEvent(
        event_type="game_finished",
        phase=Phase.FINISHED,
        day=state.day,
        payload={
            "winner": win_result.winner,
            "reason": win_result.reason,
            "winning_player_ids": win_result.winning_player_ids,
        },
    )


def build_view(
    state: GameState,
    pending: PendingActions,
    player_id: str,
    *,
    ability_policy: AbilityPolicy,
) -> GameView:
    """Build the only supported visibility-filtered player observation."""
    return observations.build_player_observation(
        state,
        pending,
        player_id,
        ability_policy=ability_policy,
    )


def _private_submission_event(
    state: GameState,
    action: Action,
    event_type: str,
) -> GameEvent:
    payload: dict[str, str | None] = {"target_id": action.target_id}
    if state.phase is Phase.DAY_DISCUSSION:
        payload = {"action_type": action.type.value}
    if action.type in {ActionType.USE_ABILITY, ActionType.PASS}:
        payload = {
            "action_type": action.type.value,
            "ability_id": action.ability_id,
        }
    return GameEvent(
        event_type=event_type,
        phase=state.phase,
        day=state.day,
        actor_id=action.player_id,
        visibility=EventVisibility.PLAYER_PRIVATE,
        payload=payload,
    )


__all__ = [
    "advance_phase",
    "build_view",
    "resolve_action",
    "validate_action",
    "validate_phase_advance",
]
