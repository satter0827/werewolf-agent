"""Private ruleset metadata helpers for game jobs."""

from __future__ import annotations

from werewolf_agent.domain.game.models import Phase
from werewolf_agent.usecase.jobs.games import GameUseCaseConfig, RulesetResult


def default_ruleset(config: GameUseCaseConfig) -> RulesetResult:
    """Return ruleset business metadata."""
    return RulesetResult(
        id=config.default_ruleset_id,
        player_count={"min": config.min_players, "max": config.max_players},
        roles=["villager", "werewolf", "seer", "knight"],
        phases=[
            Phase.NIGHT.value,
            Phase.DAY_DISCUSSION.value,
            Phase.VOTING.value,
            Phase.FINISHED.value,
        ],
        agent_types=[config.supported_agent_type],
    )
