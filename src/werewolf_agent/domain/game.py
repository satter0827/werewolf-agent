"""Aggregate root for the deterministic headless game."""

from __future__ import annotations

import random
from dataclasses import replace

from werewolf_agent.domain.definitions import RuleSet
from werewolf_agent.domain.errors import RuleViolation
from werewolf_agent.domain.rules import game_setup
from werewolf_agent.domain.rules.base import RuleContext
from werewolf_agent.domain.state import (
    Action,
    GameEvent,
    GameSetup,
    GameState,
    GameView,
    PendingActions,
    Phase,
)


class Game:
    """Stateful aggregate root with atomic, deterministic transitions."""

    def __init__(
        self,
        state: GameState,
        rules: RuleSet,
        creation_events: tuple[GameEvent, ...] = (),
    ) -> None:
        """Restore aggregate fields from validated values."""
        if state.config != rules.config:
            raise RuleViolation("rules_mismatch", "State and rule set do not match.")
        self._state = state
        self._rules = rules
        self._creation_events = tuple(creation_events)

    @classmethod
    def create(
        cls,
        setup: GameSetup,
        *,
        rules: RuleSet,
        random: random.Random,
    ) -> Game:
        """Create a game from validated setup data and injected rules."""
        state = game_setup.create_game_snapshot(rules.config, setup.players, random)
        events = (
            GameEvent(
                event_type="game_started",
                phase=state.phase,
                day=state.day,
                payload={
                    "player_count": rules.config.player_count,
                    "role_counts": dict(rules.config.role_counts),
                },
            ),
        )
        return cls(state, rules, events)

    @classmethod
    def restore(
        cls,
        state: GameState,
        *,
        rules: RuleSet,
    ) -> Game:
        """Restore a game without performing external I/O."""
        return cls(state, rules)

    def submit(self, action: Action) -> list[GameEvent]:
        """Validate and atomically apply one player action."""
        context = RuleContext(self._state, self._state.pending_actions)
        violations = list(self._rules.action.validate(action, context))
        if violations:
            raise violations[0]
        state, pending, events = self._rules.resolution.resolve(action, context)
        self._state = replace(state, pending_actions=pending)
        return events

    def advance(self, random: random.Random) -> list[GameEvent]:
        """Validate and atomically advance the current phase."""
        context = RuleContext(self._state, self._state.pending_actions)
        violations = list(self._rules.phase.violations(context))
        if violations:
            raise violations[0]
        state, pending, events = self._rules.phase.advance(context, random)
        win_result = self._rules.victory.evaluate(RuleContext(state, pending))
        if win_result is not None:
            state = replace(state, phase=Phase.FINISHED, win_result=win_result)
            events = [
                *events,
                GameEvent(
                    event_type="game_finished",
                    phase=Phase.FINISHED,
                    day=state.day,
                    payload={
                        "winner": win_result.winner,
                        "reason": win_result.reason,
                        "winning_player_ids": win_result.winning_player_ids,
                    },
                ),
            ]
        self._state = replace(state, pending_actions=pending)
        return events

    def view_for(self, player_id: str) -> GameView:
        """Return a visibility-filtered player view."""
        return self._rules.visibility.build_view(
            player_id,
            RuleContext(self._state, self._state.pending_actions),
        )

    def snapshot(self) -> GameState:
        """Return the current immutable state snapshot."""
        return self._state

    @property
    def creation_events(self) -> tuple[GameEvent, ...]:
        """Return immutable events emitted while creating this game."""
        return self._creation_events

    @property
    def pending_actions(self) -> PendingActions:
        """Return the current immutable pending-action buffer."""
        return self._state.pending_actions


__all__ = ["Game"]
