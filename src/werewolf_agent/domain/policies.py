"""Built-in stateless policies for the deterministic game core."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import replace

from werewolf_agent.domain._messages import MESSAGE_UNSUPPORTED_AGENT_ACTION
from werewolf_agent.domain.errors import GameError, RuleViolation
from werewolf_agent.domain.rules import (
    action_availability,
    day_speech,
    night_actions,
    observations,
    phase_transitions,
    voting,
)
from werewolf_agent.domain.rules.action_availability import available_actions
from werewolf_agent.domain.rules.base import (
    ActionPolicy,
    PhasePolicy,
    ResolutionPolicy,
    RuleContext,
    VictoryPolicy,
    VisibilityPolicy,
)
from werewolf_agent.domain.rules.player_rules import check_win
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


def _resolve_action(
    snapshot: GameState,
    pending_actions: PendingActions,
    action: Action,
) -> tuple[GameState, PendingActions, list[GameEvent]]:
    if action.type is ActionType.PASS:
        return snapshot, pending_actions, []
    if action.type is ActionType.SPEECH:
        next_snapshot, events = day_speech.record_day_speech(snapshot, action)
        return next_snapshot, pending_actions, events
    if action.type is ActionType.VOTE:
        votes = voting.record_vote(
            snapshot,
            snapshot.config,
            pending_actions.votes,
            action,
            candidates=pending_actions.revote_candidates,
        )
        return (
            snapshot,
            replace(pending_actions, votes=votes),
            [
                GameEvent(
                    event_type="vote_submitted",
                    phase=snapshot.phase,
                    day=snapshot.day,
                    actor_id=action.player_id,
                    visibility=EventVisibility.PLAYER_PRIVATE,
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
            replace(pending_actions, night_actions=actions),
            [
                GameEvent(
                    event_type="night_action_submitted",
                    phase=snapshot.phase,
                    day=snapshot.day,
                    actor_id=action.player_id,
                    visibility=EventVisibility.PLAYER_PRIVATE,
                    payload={"action_type": action.type.value},
                )
            ],
        )
    raise GameError(MESSAGE_UNSUPPORTED_AGENT_ACTION)


def _advance_without_victory(
    snapshot: GameState,
    pending_actions: PendingActions,
    random_source: random.Random,
) -> tuple[GameState, PendingActions, list[GameEvent]]:
    outcome = phase_transitions.advance_game_phase(
        snapshot,
        snapshot.config,
        pending_actions.votes,
        pending_actions.night_actions,
        random_source,
        vote_round=pending_actions.vote_round,
        victory_evaluator=lambda _state: None,
    )
    next_pending = replace(
        pending_actions,
        votes={} if outcome.clear_votes else pending_actions.votes,
        night_actions={} if outcome.clear_night_actions else pending_actions.night_actions,
        vote_round=outcome.next_vote_round,
        revote_candidates=outcome.revote_candidates,
    )
    return outcome.snapshot, next_pending, outcome.events


class StandardActionPolicy(ActionPolicy):
    """Validate actions with the standard configured game rules."""

    def validate(self, action: Action, context: RuleContext) -> Sequence[RuleViolation]:
        """Return violations produced by the configured standard validators."""
        try:
            action_availability.require_action_available(context.state, context.pending, action)
        except GameError as exc:
            return [RuleViolation("action_not_available", str(exc))]
        return ()


class StandardResolutionPolicy(ResolutionPolicy):
    """Resolve accepted actions with the standard game algorithms."""

    def resolve(
        self,
        action: Action,
        context: RuleContext,
    ) -> tuple[GameState, PendingActions, list[GameEvent]]:
        """Resolve one action without retaining policy state."""
        return _resolve_action(context.state, context.pending, action)


class RequiredActionsPhasePolicy(PhasePolicy):
    """Prevent resolution while required player actions are missing."""

    def violations(self, context: RuleContext) -> Sequence[RuleViolation]:
        """Return a violation while required actions remain outstanding."""
        state = context.state
        if not state.config.rules.require_all_actions_before_advance:
            return ()
        if state.phase not in {Phase.NIGHT, Phase.VOTING}:
            return ()
        missing = [
            player.id
            for player in state.players.values()
            if player.is_alive and available_actions(state, context.pending, player.id)
        ]
        if not missing:
            return ()
        return [
            RuleViolation(
                "required_actions_missing",
                "Required actions are missing.",
                context={"phase": state.phase.value, "player_ids": tuple(sorted(missing))},
            )
        ]

    def advance(
        self,
        context: RuleContext,
        random_source: random.Random,
    ) -> tuple[GameState, PendingActions, list[GameEvent]]:
        """Advance one completed phase without evaluating victory."""
        return _advance_without_victory(context.state, context.pending, random_source)


class FactionBalanceVictoryPolicy(VictoryPolicy):
    """Evaluate the standard faction elimination and parity rules."""

    def evaluate(self, context: RuleContext) -> WinResult | None:
        """Return the configured two-faction victory result, when decided."""
        return check_win(context.state)


class StandardVisibilityPolicy(VisibilityPolicy):
    """Build the standard role-aware player observation."""

    def build_view(self, player_id: str, context: RuleContext) -> GameView:
        """Return a role-aware view with domain-validated legal targets."""
        return observations.build_player_observation(context.state, context.pending, player_id)


__all__ = [
    "FactionBalanceVictoryPolicy",
    "RequiredActionsPhasePolicy",
    "StandardActionPolicy",
    "StandardResolutionPolicy",
    "StandardVisibilityPolicy",
]
