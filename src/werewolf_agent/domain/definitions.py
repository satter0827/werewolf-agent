"""Configuration data and the single executable-rule factory."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from werewolf_agent.domain._model import frozen_mapping
from werewolf_agent.domain.state import AbilityDefinition, GameConfig, LocalRules, RoleCatalog


@dataclass(frozen=True)
class RuleSetDefinition:
    """Validated data used to construct one executable rule set."""

    player_count: int
    role_counts: Mapping[str, int]
    rules: LocalRules
    roles: RoleCatalog
    abilities: Mapping[str, AbilityDefinition]

    def __post_init__(self) -> None:
        """Freeze nested mappings after construction."""
        object.__setattr__(self, "role_counts", frozen_mapping(self.role_counts))
        object.__setattr__(self, "abilities", frozen_mapping(self.abilities))


@dataclass(frozen=True)
class RuleSet:
    """Validated executable configuration for one game."""

    config: GameConfig


def build_game_rules(definition: RuleSetDefinition) -> RuleSet:
    """Build the only supported deterministic rule pipeline from data."""
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
