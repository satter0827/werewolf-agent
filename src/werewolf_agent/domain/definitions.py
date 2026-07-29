"""Configuration data and the single executable-rule factory."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from werewolf_agent.domain._model import frozen_mapping
from werewolf_agent.domain.state import AbilityDefinition, GameConfig, LocalRules, RoleCatalog


@dataclass(frozen=True)
class RuleSetDefinition:
    """実行可能なrule setの構築に使う検証済みdataを表す。"""

    player_count: int
    role_counts: Mapping[str, int]
    rules: LocalRules
    roles: RoleCatalog
    abilities: Mapping[str, AbilityDefinition]

    def __post_init__(self) -> None:
        """構築後に入れ子のmappingを固定する。"""
        object.__setattr__(self, "role_counts", frozen_mapping(self.role_counts))
        object.__setattr__(self, "abilities", frozen_mapping(self.abilities))


@dataclass(frozen=True)
class RuleSet:
    """一つのゲームで実行する検証済み設定を表す。"""

    config: GameConfig


def build_game_rules(definition: RuleSetDefinition) -> RuleSet:
    """Dataから唯一の対応済み決定的rule pipelineを構築する。"""
    return RuleSet(
        config=GameConfig(
            player_count=definition.player_count,
            role_counts=definition.role_counts,
            rules=definition.rules,
            roles=definition.roles,
            abilities=definition.abilities,
        ),
    )


__all__ = ["RuleSet", "RuleSetDefinition", "build_game_rules"]
