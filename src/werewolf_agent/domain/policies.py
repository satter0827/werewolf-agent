"""Built-in stateless policies for the deterministic game core."""

from __future__ import annotations

import random
from collections.abc import Sequence

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
    DomainEvent,
    EventVisibility,
    GameSnapshot,
    Observation,
    PendingActions,
    Phase,
    WinResult,
)


def _resolve_action(
    snapshot: GameSnapshot,
    pending_actions: PendingActions,
    action: Action,
) -> tuple[GameSnapshot, PendingActions, list[DomainEvent]]:
    if action.type is ActionType.PASS:
        return snapshot, pending_actions, []
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
            pending_actions.model_copy(update={"night_actions": actions}),
            [
                DomainEvent(
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
    snapshot: GameSnapshot,
    pending_actions: PendingActions,
    random_source: random.Random,
) -> tuple[GameSnapshot, PendingActions, list[DomainEvent]]:
    outcome = phase_transitions.advance_game_phase(
        snapshot,
        snapshot.config,
        pending_actions.votes,
        pending_actions.night_actions,
        random_source,
        victory_evaluator=lambda _state: None,
    )
    updates: dict[str, object] = {}
    if outcome.clear_votes:
        updates["votes"] = {}
    if outcome.clear_night_actions:
        updates["night_actions"] = {}
    next_pending = pending_actions.model_copy(update=updates) if updates else pending_actions
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
    ) -> tuple[GameSnapshot, PendingActions, list[DomainEvent]]:
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
    ) -> tuple[GameSnapshot, PendingActions, list[DomainEvent]]:
        """Advance one completed phase without evaluating victory."""
        return _advance_without_victory(context.state, context.pending, random_source)


class FactionBalanceVictoryPolicy(VictoryPolicy):
    """Evaluate the standard faction elimination and parity rules."""

    def evaluate(self, context: RuleContext) -> WinResult | None:
        """Return the configured two-faction victory result, when decided."""
        return check_win(context.state)


class StandardVisibilityPolicy(VisibilityPolicy):
    """Build the standard role-aware player observation."""

    def build_view(self, player_id: str, context: RuleContext) -> Observation:
        """Return a role-aware view with domain-validated legal targets."""
        return observations.build_player_observation(context.state, context.pending, player_id)


__all__ = [
    "FactionBalanceVictoryPolicy",
    "RequiredActionsPhasePolicy",
    "StandardActionPolicy",
    "StandardResolutionPolicy",
    "StandardVisibilityPolicy",
]
