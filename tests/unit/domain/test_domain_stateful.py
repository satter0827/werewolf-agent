"""Capability駆動でdomain aggregateの状態遷移を探索する。"""

from __future__ import annotations

import random

import pytest
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule

from werewolf_agent.adapters.application_bridge import build_setup_catalog
from werewolf_agent.application.players import generate_players
from werewolf_agent.application.randomness import namespace_seed
from werewolf_agent.application.rules import rule_definition_from_values
from werewolf_agent.domain import (
    Action,
    ActionType,
    Game,
    GameSetup,
    Phase,
    Player,
    build_game_rules,
)
from werewolf_agent.domain.errors import RuleViolation

SETUP_CATALOG = build_setup_catalog()
SETUP_PRESETS = tuple(SETUP_CATALOG.template_order)


def _game(preset_id: str, seed: int) -> Game:
    document = SETUP_CATALOG.require_document(preset_id)
    mechanics = document.mechanics
    player_count = sum(mechanics.role_counts.values())
    rules = build_game_rules(
        rule_definition_from_values(
            player_count=sum(mechanics.role_counts.values()),
            role_counts=mechanics.role_counts,
            rules=mechanics.rules.model_dump(mode="json"),
            roles={key: value.model_dump(mode="json") for key, value in mechanics.roles.items()},
            abilities={
                key: value.model_dump(mode="json") for key, value in mechanics.abilities.items()
            },
        )
    )
    generated = generate_players(document.player_generation, player_count=player_count, seed=seed)
    return Game.create(
        GameSetup(
            players=tuple(Player(id=item.player_id, name=item.profile.name) for item in generated)
        ),
        rules=rules,
        random=random.Random(namespace_seed(seed, "role_assignment")),
    )


class GameStateMachine(RuleBasedStateMachine):
    """公開capabilityだけから有効操作を組み立てる。"""

    def __init__(self) -> None:
        super().__init__()
        self.game = _game(SETUP_PRESETS[0], 73)
        self.random = random.Random(191)

    @initialize(
        preset_id=st.sampled_from(SETUP_PRESETS),
        seed=st.integers(min_value=0, max_value=2**31 - 1),
    )
    def initialize_game(self, preset_id: str, seed: int) -> None:
        """Packaged presetとseedから探索対象gameを初期化する。"""
        self.game = _game(preset_id, seed)
        self.random = random.Random(namespace_seed(seed, "stateful-actions"))

    @rule()
    def submit_available_action(self) -> None:
        if self.game.snapshot().phase is Phase.FINISHED:
            return
        candidates = []
        for player_id in self.game.snapshot().players:
            view = self.game.view_for(player_id)
            for available in view.available_actions:
                targets = view.legal_targets.get(available.key, ())
                candidates.append((player_id, available, targets))
        if not candidates:
            return
        player_id, available, targets = candidates[self.random.randrange(len(candidates))]
        action = Action(
            type=available.type,
            player_id=player_id,
            ability_id=available.ability_id,
            target_id=self.random.choice(targets) if targets else None,
            message="状況を確認します。" if available.type is ActionType.SPEECH else None,
        )
        before = self.game.snapshot()
        self.game.submit(action)
        assert self.game.snapshot() is not before

    @rule()
    def advance_or_preserve_state(self) -> None:
        if self.game.snapshot().phase is Phase.FINISHED:
            return
        before = self.game.snapshot()
        try:
            self.game.advance(self.random)
        except RuleViolation:
            assert self.game.snapshot() == before

    @rule()
    def rejected_actor_preserves_state(self) -> None:
        before = self.game.snapshot()
        with pytest.raises(RuleViolation):
            self.game.submit(Action.pass_("unknown-player"))
        assert self.game.snapshot() == before

    @invariant()
    def views_do_not_reveal_unknown_roles(self) -> None:
        for player_id in self.game.snapshot().players:
            view = self.game.view_for(player_id)
            for player in view.players:
                if player.id != player_id and player.id not in view.known_roles:
                    assert player.role is None

    @invariant()
    def finished_games_reject_further_progress(self) -> None:
        if self.game.snapshot().phase is not Phase.FINISHED:
            return
        before = self.game.snapshot()
        with pytest.raises(RuleViolation):
            self.game.advance(self.random)
        assert self.game.snapshot() == before


TestGameStateMachine = pytest.mark.monkey(GameStateMachine.TestCase)


def test_public_actions_do_not_accept_ability_ids() -> None:
    vote = Action(type=ActionType.VOTE, player_id="p1", target_id="p2")
    speech = Action(type=ActionType.SPEECH, player_id="p1", message="確認します。")

    assert vote.ability_id is None
    assert speech.ability_id is None
