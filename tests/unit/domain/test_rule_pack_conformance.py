"""Coreと外部Rule Packへ同じ公開契約テストを適用する。"""

from __future__ import annotations

from dataclasses import replace

from werewolf_agent.adapters.application_bridge import build_setup_catalog
from werewolf_agent.domain import (
    RULE_PACK_CONTRACT_VERSION,
    CompiledRuleSet,
    CoreRulePack,
    DiscussionRelation,
    GameSetup,
    Player,
    RulePackManifest,
    RuleSetDefinition,
    assert_rule_pack_contract,
)
from werewolf_agent.setup import generate_players, rule_definition_from_values

_SEED = 73


class _ExternalMirrorPack:
    """Coreの意味論を外部provider identityで提供するcontract fixture。"""

    @property
    def manifest(self) -> RulePackManifest:
        return RulePackManifest(
            provider_id="external-mirror",
            contract_version=RULE_PACK_CONTRACT_VERSION,
            implementation_version="1.0.0",
            fingerprint="3" * 64,
        )

    def compile(self, definition: RuleSetDefinition) -> CompiledRuleSet:
        return replace(CoreRulePack().compile(definition), manifest=self.manifest)


def _inputs() -> tuple[RuleSetDefinition, GameSetup]:
    document = build_setup_catalog().require_document("standard_6")
    mechanics = document.mechanics
    player_count = sum(mechanics.role_counts.values())
    definition = rule_definition_from_values(
        player_count=player_count,
        role_counts=mechanics.role_counts,
        discussion=mechanics.discussion.to_mapping(),
        voting=mechanics.voting.to_mapping(),
        night=mechanics.night.to_mapping(),
        lifecycle=mechanics.lifecycle.to_mapping(),
        roles={key: value.to_mapping() for key, value in mechanics.roles.items()},
        abilities={key: value.to_mapping() for key, value in mechanics.abilities.items()},
    )
    generated = generate_players(document.player_generation, player_count=player_count, seed=_SEED)
    setup = GameSetup(tuple(Player(item.player_id, item.profile.name) for item in generated))
    return definition, setup


def test_core_rule_pack_uses_the_public_contract_kit() -> None:
    """組み込みproviderへ公開契約をそのまま適用する。"""
    definition, setup = _inputs()
    assert_rule_pack_contract(CoreRulePack(), definition=definition, setup=setup, seed=_SEED)


def test_external_rule_pack_uses_the_public_contract_kit() -> None:
    """外部providerへ利用者と同じ公開契約を適用する。"""
    definition, setup = _inputs()
    assert_rule_pack_contract(_ExternalMirrorPack(), definition=definition, setup=setup, seed=_SEED)


def test_contract_kit_honors_support_only_response_setup() -> None:
    definition, setup = _inputs()
    opening, response = definition.discussion.stages
    definition = replace(
        definition,
        discussion=replace(
            definition.discussion,
            stages=(
                opening,
                replace(response, allowed_relations=(DiscussionRelation.SUPPORT,)),
            ),
        ),
    )

    assert_rule_pack_contract(CoreRulePack(), definition=definition, setup=setup, seed=_SEED)
