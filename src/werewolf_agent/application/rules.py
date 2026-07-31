"""Persisted application stateをDomain Rule Definitionへ復元する."""

from __future__ import annotations

from werewolf_agent.domain import RuleSetDefinition
from werewolf_agent.domain.state import (
    GameState,
)


def rule_definition_from_state(
    state: GameState,
) -> RuleSetDefinition:
    """Restore typed rule data from one persisted aggregate snapshot."""
    config = state.config
    return RuleSetDefinition(
        player_count=config.player_count,
        role_counts=config.role_counts,
        rules=config.rules,
        roles=config.roles,
        abilities=config.abilities,
    )


__all__ = ["rule_definition_from_state"]
