"""Definition converters used by internal use case workflows."""

from __future__ import annotations

from werewolf_agent.commons.shared.definitions import (
    GameRoleDefinitions,
    LocalRulesDefinition,
    PlayerRoster,
)
from werewolf_agent.domain.game.models import LocalRules, RoleCatalog
from werewolf_agent.domain.game.models import RoleDefinition as DomainRoleDefinition
from werewolf_agent.domain.llm.models import PlayerProfile, PlayerProfileCatalog


def local_rules_to_domain(definitions: LocalRulesDefinition) -> LocalRules:
    """Convert local rule settings to a domain rule model."""
    return LocalRules.model_validate(definitions.model_dump(mode="json"))


def to_role_catalog(definitions: GameRoleDefinitions) -> RoleCatalog:
    """Convert role definitions to a domain role catalog."""
    return RoleCatalog(
        roles={
            role_id: DomainRoleDefinition.model_validate(definition.model_dump(mode="json"))
            for role_id, definition in definitions.roles.items()
        }
    )


def to_player_profiles(definitions: PlayerRoster) -> PlayerProfileCatalog:
    """Convert LLM player definitions to a domain player profile catalog."""
    return PlayerProfileCatalog(
        profiles={
            profile_id: PlayerProfile.model_validate(definition.model_dump(mode="json"))
            for profile_id, definition in definitions.players.items()
        }
    )
