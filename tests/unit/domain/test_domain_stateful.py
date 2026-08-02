"""Capability駆動でdomain aggregateの状態遷移を探索する。"""

from __future__ import annotations

import random

import pytest
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule

from werewolf_agent.adapters.application_bridge import build_setup_catalog
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
from werewolf_agent.setup import generate_players, namespace_seed, rule_definition_from_values

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
            discussion=mechanics.discussion.to_mapping(),
            voting=mechanics.voting.to_mapping(),
            night=mechanics.night.to_mapping(),
            lifecycle=mechanics.lifecycle.to_mapping(),
            roles={key: value.to_mapping() for key, value in mechanics.roles.items()},
            abilities={key: value.to_mapping() for key, value in mechanics.abilities.items()},
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
        view = self.game.view_for(player_id)
        if available.type is ActionType.VOTE:
            viable_targets = [
                target
                for target in targets
                if any(
                    target in {evidence.actor_id, evidence.topic_id}
                    for evidence in view.legal_evidence.get(available.key, ())
                )
            ]
            if not viable_targets:
                return
            target_id = self.random.choice(viable_targets)
        else:
            target_id = self.random.choice(targets) if targets else None
        if available.type is ActionType.SPEECH:
            round_ = view.discussion_round
            speeches = {speech.speech_id: speech for speech in view.history.speeches}
            reference_id = (
                next(
                    reference
                    for reference in round_.reference_ids
                    if speeches[reference].player_id != player_id
                )
                if round_ is not None and round_.reference_ids
                else None
            )
            referenced = speeches.get(reference_id) if reference_id else None
            topic_id = (
                referenced.topic_id
                if referenced is not None
                else next(
                    player.id
                    for player in view.players
                    if player.id != player_id and player.is_alive
                )
            )
            action = Action.speech(
                player_id,
                (
                    f"{reference_id}を踏まえて状況を再検討します。"
                    if reference_id is not None
                    else f"{player_id}の視点から状況を確認します。"
                ),
                topic_id=topic_id,
                position=(
                    "oppose"
                    if referenced is not None and referenced.position.value == "support"
                    else "support"
                ),
                relation="challenge" if referenced is not None else "independent",
                evidence_id=reference_id,
                response_to_id=reference_id,
            )
        elif available.type is ActionType.VOTE and target_id is not None:
            evidence_id = next(
                evidence.evidence_id
                for evidence in view.legal_evidence[available.key]
                if target_id in {evidence.actor_id, evidence.topic_id}
            )
            action = Action.vote(
                player_id,
                target_id,
                reason="公開情報から判断します。",
                evidence_id=evidence_id,
            )
        elif available.type is ActionType.USE_ABILITY:
            action = Action.use_ability(player_id, available.ability_id or "", target_id)
        else:
            action = Action.pass_(player_id)
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
    vote = Action.vote("p1", "p2", reason="疑わしいため", evidence_id="speech:p2")
    speech = Action.speech(
        "p1",
        "確認します。",
        topic_id="p2",
        position="undecided",
        relation="independent",
    )

    assert vote.ability_id is None
    assert speech.ability_id is None
