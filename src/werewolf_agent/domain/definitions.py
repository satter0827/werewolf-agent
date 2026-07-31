"""Configuration data and the single executable-rule factory."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from werewolf_agent.domain._model import frozen_mapping
from werewolf_agent.domain.rule_packs import (
    CORE_RULE_PACK_FINGERPRINT,
    CORE_RULE_PACK_ID,
    CORE_RULE_PACK_IMPLEMENTATION_VERSION,
    RULE_PACK_CONTRACT_VERSION,
    CompiledRuleSet,
    CoreVictoryPolicy,
    RulePackManifest,
)
from werewolf_agent.domain.rules.voting import CoreVotingPolicy
from werewolf_agent.domain.state import AbilityDefinition, GameConfig, LocalRules, RoleCatalog


@dataclass(frozen=True)
class RuleSetDefinition:
    """実行可能なrule setの構築に使う検証済みdataを表す."""

    player_count: int
    role_counts: Mapping[str, int]
    rules: LocalRules
    roles: RoleCatalog
    abilities: Mapping[str, AbilityDefinition]

    def __post_init__(self) -> None:
        """構築後に入れ子のmappingを固定する."""
        object.__setattr__(self, "role_counts", frozen_mapping(self.role_counts))
        object.__setattr__(self, "abilities", frozen_mapping(self.abilities))


class CoreRulePack:
    """現在の組み込み規則を同じProvider契約でcompileする."""

    @property
    def manifest(self) -> RulePackManifest:
        """組み込みRule Packのversion付きmanifestを返す."""
        return RulePackManifest(
            provider_id=CORE_RULE_PACK_ID,
            contract_version=RULE_PACK_CONTRACT_VERSION,
            implementation_version=CORE_RULE_PACK_IMPLEMENTATION_VERSION,
            fingerprint=CORE_RULE_PACK_FINGERPRINT,
        )

    def compile(self, definition: RuleSetDefinition) -> CompiledRuleSet:
        """検証済みdataを組み込みpolicy付きrulesetへ変換する."""
        return CompiledRuleSet(
            config=GameConfig(
                player_count=definition.player_count,
                role_counts=definition.role_counts,
                rules=definition.rules,
                roles=definition.roles,
                abilities=definition.abilities,
            ),
            manifest=self.manifest,
            voting_policy=CoreVotingPolicy(),
            victory_policy=CoreVictoryPolicy(),
        )


def build_game_rules(definition: RuleSetDefinition) -> CompiledRuleSet:
    """Dataを組み込みRule Packでcompileする."""
    return CoreRulePack().compile(definition)


__all__ = ["CoreRulePack", "RuleSetDefinition", "build_game_rules"]
