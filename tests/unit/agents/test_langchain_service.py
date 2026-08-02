import pytest
from pydantic import ValidationError

from werewolf_agent.adapters.llm.models import (
    AgentActionType,
    AgentAvailableAction,
    AgentModelDecision,
)


def test_agent_ability_decision_uses_generic_action_and_ability_id() -> None:
    decision = AgentModelDecision(
        type=AgentActionType.USE_ABILITY,
        ability_id="custom_scan",
        target_id="p2",
    )

    assert decision.type is AgentActionType.USE_ABILITY
    assert decision.ability_id == "custom_scan"
    assert AgentAvailableAction(type="use_ability", ability_id="custom_scan").key == (
        "use_ability:custom_scan"
    )


def test_agent_ability_decision_requires_ability_id() -> None:
    with pytest.raises(ValidationError, match="ability_id"):
        AgentModelDecision(type="use_ability", target_id="p2")
