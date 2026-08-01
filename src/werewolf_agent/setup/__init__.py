"""Headless SDKの決定的なsetup primitives."""

from werewolf_agent.setup.checksums import checksum_payload
from werewolf_agent.setup.document import (
    ABILITY_KINDS,
    SETUP_SCHEMA_VERSION,
    AbilityDefinition,
    DiscussionDefinition,
    GameSetupDocument,
    LifecycleDefinition,
    MechanicsDefinition,
    NightDefinition,
    RoleDefinition,
    ThemeDefinition,
    VotingDefinition,
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
    "DiscussionDefinition",
    "GameSetupDocument",
    "GeneratedPlayer",
    "LifecycleDefinition",
    "MechanicsDefinition",
    "NightDefinition",
    "PlayerGenerationDefinition",
    "PlayerIdentityDefinition",
    "PlayerProfile",
    "PrivateStrategyDefinition",
    "PublicPersonaDefinition",
    "RiskTolerance",
    "RoleDefinition",
    "ThemeDefinition",
    "VotingDefinition",
    "checksum_payload",
    "generate_players",
    "namespace_seed",
    "profiles_by_player",
    "rule_definition_from_values",
]
