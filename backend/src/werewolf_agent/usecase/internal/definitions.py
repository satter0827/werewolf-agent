"""Definition converters used by internal use case workflows."""

from __future__ import annotations

from werewolf_agent.commons.shared.definitions import (
    GameRoleDefinitions,
    GameRuleDefinitions,
    LlmAgentDefinitions,
)
from werewolf_agent.domain.game.models import LocalRules, RoleCatalog
from werewolf_agent.domain.game.models import RoleDefinition as DomainRoleDefinition
from werewolf_agent.domain.llm.models import AgentProfile, AgentProfileCatalog


def to_local_rules(definitions: GameRuleDefinitions) -> LocalRules:
    """Convert game rule definitions to a domain rule model."""
    return LocalRules.model_validate(definitions.local_rules.model_dump(mode="json"))


def to_role_catalog(definitions: GameRoleDefinitions) -> RoleCatalog:
    """Convert role definitions to a domain role catalog."""
    return RoleCatalog(
        roles={
            role_id: DomainRoleDefinition.model_validate(definition.model_dump(mode="json"))
            for role_id, definition in definitions.roles.items()
        }
    )


def to_agent_profiles(definitions: LlmAgentDefinitions) -> AgentProfileCatalog:
    """Convert LLM agent definitions to a domain agent profile catalog."""
    return AgentProfileCatalog(
        agents={
            agent_id: AgentProfile.model_validate(definition.model_dump(mode="json"))
            for agent_id, definition in definitions.agents.items()
        }
    )
