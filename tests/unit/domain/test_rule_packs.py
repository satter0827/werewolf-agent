"""外部Rule Packの明示注入と勝敗policy契約を検証する."""

from __future__ import annotations

import random

import pytest

from werewolf_agent.domain import (
    CompiledRuleSet,
    CoreRulePack,
    Game,
    GameSetup,
    GameState,
    LocalRules,
    Player,
    RoleCatalog,
    RoleDefinition,
    RulePackManifest,
    RulePolicyRegistry,
    RuleSetDefinition,
    WinResult,
)
from werewolf_agent.domain.rule_packs import RULE_PACK_CONTRACT_VERSION


def _definition() -> RuleSetDefinition:
    return RuleSetDefinition(
        player_count=3,
        role_counts={"villager": 2, "werewolf": 1},
        rules=LocalRules(
            day_speech_limit_per_player=1,
            allow_self_vote=False,
            allow_vote_revision=False,
            allow_night_action_revision=False,
            vote_tie_resolution="no_elimination",
            starting_phase="day_discussion",
            reveal_role_on_death=False,
        ),
        roles=RoleCatalog(
            {
                "villager": RoleDefinition("village", "village"),
                "werewolf": RoleDefinition("werewolf", "werewolf"),
            }
        ),
        abilities={},
    )


class ImmediateVillageVictory:
    """最初の進行で村人勝利を返す外部test policy."""

    def evaluate(self, state: GameState) -> WinResult:
        """現在の村人陣営playerを勝者として返す."""
        winners = tuple(
            player.id
            for player in state.players.values()
            if player.role is not None
            and state.config.roles.victory_team_for_role(player.role) == "village"
        )
        return WinResult(
            winner="village",
            reason="external_test_condition",
            day=state.day,
            winning_player_ids=winners,
        )


class ExternalVictoryPack:
    """Coreのconfig構築と外部勝敗policyを組み合わせるtest provider."""

    @property
    def manifest(self) -> RulePackManifest:
        """外部実装を識別するmanifestを返す."""
        return RulePackManifest(
            provider_id="external-victory",
            contract_version=RULE_PACK_CONTRACT_VERSION,
            implementation_version="1.0.0",
            fingerprint="external-victory-1",
        )

    def compile(self, definition: RuleSetDefinition) -> CompiledRuleSet:
        """Core configへ外部勝敗policyを明示注入する."""
        core = CoreRulePack().compile(definition)
        return CompiledRuleSet(
            config=core.config,
            manifest=self.manifest,
            victory_policy=ImmediateVillageVictory(),
        )


class InvalidVictoryPolicy:
    """Stateと矛盾する勝者一覧を返すfault policy."""

    def evaluate(self, state: GameState) -> WinResult:
        """村人勝利へ人狼playerだけを含めた不正Outcomeを返す."""
        wolf_id = next(
            player.id
            for player in state.players.values()
            if player.role is not None
            and state.config.roles.victory_team_for_role(player.role) == "werewolf"
        )
        return WinResult(
            winner="village",
            reason="invalid_external_outcome",
            day=state.day,
            winning_player_ids=(wolf_id,),
        )


def test_external_provider_is_used_only_after_explicit_registration() -> None:
    provider = ExternalVictoryPack()
    registry = RulePolicyRegistry((CoreRulePack(), provider))

    assert registry.provider_ids == ("core", "external-victory")
    assert registry.require("external-victory") is provider
    with pytest.raises(ValueError, match="unknown rule pack provider"):
        registry.require("not-registered")
    with pytest.raises(ValueError, match="duplicate rule pack provider"):
        RulePolicyRegistry((provider, provider))


def test_external_victory_policy_changes_outcome_without_mutating_state() -> None:
    rules = ExternalVictoryPack().compile(_definition())
    game = Game.create(
        GameSetup(
            (
                Player("p1", "Alice"),
                Player("p2", "Bob"),
                Player("p3", "Carol"),
            )
        ),
        rules=rules,
        random=random.Random(7),
    )

    events = game.advance(random.Random(11))

    assert game.snapshot().winner_id == "village"
    assert game.snapshot().win_result is not None
    assert game.snapshot().win_result.reason == "external_test_condition"
    assert events[-1].event_type == "game_finished"


def test_invalid_external_outcome_is_rejected_atomically() -> None:
    core = CoreRulePack().compile(_definition())
    rules = CompiledRuleSet(
        config=core.config,
        manifest=ExternalVictoryPack().manifest,
        victory_policy=InvalidVictoryPolicy(),
    )
    game = Game.create(
        GameSetup(
            (
                Player("p1", "Alice"),
                Player("p2", "Bob"),
                Player("p3", "Carol"),
            )
        ),
        rules=rules,
        random=random.Random(7),
    )
    before = game.snapshot()

    with pytest.raises(ValueError, match="winning player ids"):
        game.advance(random.Random(11))

    assert game.snapshot() is before
