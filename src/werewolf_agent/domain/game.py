"""決定的なheadlessゲームのaggregate rootを定義する."""

from __future__ import annotations

import random
from dataclasses import replace

from werewolf_agent.domain.errors import RuleViolation
from werewolf_agent.domain.rule_packs import CompiledRuleSet
from werewolf_agent.domain.rules import engine, game_setup
from werewolf_agent.domain.state import (
    Action,
    GameEvent,
    GameSetup,
    GameState,
    GameView,
    PendingActions,
)


class Game:
    """Atomicで決定的な遷移を行うstateful aggregate rootを表す."""

    def __init__(
        self,
        state: GameState,
        rules: CompiledRuleSet,
        creation_events: tuple[GameEvent, ...] = (),
    ) -> None:
        """検証済みの値からaggregate fieldを復元する."""
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
        rules: CompiledRuleSet,
        random: random.Random,
    ) -> Game:
        """検証済みsetup dataと注入した規則からゲームを作成する."""
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
        rules: CompiledRuleSet,
    ) -> Game:
        """外部I/Oを行わずゲームを復元する."""
        return cls(state, rules)

    def submit(self, action: Action) -> list[GameEvent]:
        """一つのplayer actionを検証してatomicに適用する."""
        engine.validate_action(self._state, self._state.pending_actions, action)
        state, pending, events = engine.resolve_action(
            self._state,
            self._state.pending_actions,
            action,
        )
        self._state = replace(state, pending_actions=pending)
        return events

    def advance(self, random: random.Random) -> list[GameEvent]:
        """現在のphaseを検証してatomicに進める."""
        engine.validate_phase_advance(self._state, self._state.pending_actions)
        state, pending, events = engine.advance_phase(
            self._state,
            self._state.pending_actions,
            random,
            voting_policy=self._rules.voting_policy,
            victory_policy=self._rules.victory_policy,
        )
        self._state = replace(state, pending_actions=pending)
        return events

    def view_for(self, player_id: str) -> GameView:
        """可視性でfilterしたplayer viewを返す."""
        return engine.build_view(self._state, self._state.pending_actions, player_id)

    def snapshot(self) -> GameState:
        """現在のimmutableなstate snapshotを返す."""
        return self._state

    @property
    def creation_events(self) -> tuple[GameEvent, ...]:
        """ゲーム作成時に生成したimmutable eventを返す."""
        return self._creation_events

    @property
    def pending_actions(self) -> PendingActions:
        """現在のimmutableなpending-action bufferを返す."""
        return self._state.pending_actions


__all__ = ["Game"]
