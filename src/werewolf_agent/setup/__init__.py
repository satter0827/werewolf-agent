"""Headless SDKの決定的なsetup primitives."""

from werewolf_agent.setup.checksums import checksum_payload
from werewolf_agent.setup.document import (
    ABILITY_KINDS,
    SETUP_SCHEMA_VERSION,
    AbilityDefinition,
    GameSetupDocument,
    LocalRulesDefinition,
    MechanicsDefinition,
    RoleDefinition,
    ThemeDefinition,
    rule_definition_from_values,
)
from werewolf_agent.setup.players import (
    GeneratedPlayer,
    PlayerGenerationDefinition,
    PlayerIdentityDefinition,
    PlayerProfile,
    PrivateStrategyDefinition,
    PublicPersonaDefinition,
    RiskTolerance,
    generate_players,
    profiles_by_player,
)
from werewolf_agent.setup.randomness import namespace_seed

__all__ = [
    "ABILITY_KINDS",
    "SETUP_SCHEMA_VERSION",
    "AbilityDefinition",
    "GameSetupDocument",
    "GeneratedPlayer",
    "LocalRulesDefinition",
    "MechanicsDefinition",
    "PlayerGenerationDefinition",
    "PlayerIdentityDefinition",
    "PlayerProfile",
    "PrivateStrategyDefinition",
    "PublicPersonaDefinition",
    "RiskTolerance",
    "RoleDefinition",
    "ThemeDefinition",
    "checksum_payload",
    "generate_players",
    "namespace_seed",
    "profiles_by_player",
    "rule_definition_from_values",
]
