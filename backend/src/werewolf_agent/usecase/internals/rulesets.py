"""Ruleset metadata exposed through use cases."""

from __future__ import annotations

from werewolf_agent.domain.models import Phase
from werewolf_agent.usecase.jobs.models import GameUseCaseSettings, RulesetResponse


def default_ruleset(settings: GameUseCaseSettings) -> RulesetResponse:
    """Return the public MVP ruleset metadata."""
    return RulesetResponse(
        id=settings.default_ruleset_id,
        name=settings.default_ruleset_name,
        description=settings.default_ruleset_description,
        player_count={"min": settings.min_players, "max": settings.max_players},
        roles=[
            {"id": "villager", "name": "村人"},
            {"id": "werewolf", "name": "人狼"},
            {"id": "seer", "name": "占い師"},
            {"id": "knight", "name": "騎士"},
        ],
        phases=[
            {"id": Phase.NIGHT.value, "name": "夜"},
            {"id": Phase.DAY_DISCUSSION.value, "name": "昼チャット"},
            {"id": Phase.VOTING.value, "name": "投票"},
            {"id": Phase.FINISHED.value, "name": "終了"},
        ],
        agent_types=[
            {
                "id": settings.supported_agent_type,
                "name": settings.supported_agent_name,
            }
        ],
    )
