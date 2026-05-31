"""Internal ruleset metadata helpers for game jobs."""

from __future__ import annotations

from werewolf_agent.commons.shared.definitions import GameDefinitions
from werewolf_agent.usecase.jobs.games import GameUseCaseConfig, RulesetResult


def default_ruleset(config: GameUseCaseConfig, definitions: GameDefinitions) -> RulesetResult:
    """Return ruleset business metadata."""
    return RulesetResult(
        player_count={"min": config.min_players, "max": config.max_players},
        roles={
            role_id: definition.model_dump(mode="json")
            for role_id, definition in definitions.roles.roles.items()
        },
        default_role_counts=definitions.roles.default_counts_for(config.default_player_count),
        default_rules=definitions.rules.local_rules,
    )
