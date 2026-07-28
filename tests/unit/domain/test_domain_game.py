from __future__ import annotations

import pytest

from werewolf_agent.domain import Action, ActionType, AvailableAction
from werewolf_agent.domain.state import AbilityDefinition, Phase


@pytest.mark.parametrize(
    ("kind", "target_policy", "knowledge_mode", "phase", "source_kinds"),
    [
        ("attack", "other_alive", None, Phase.NIGHT, ()),
        ("inspect", "other_alive", None, Phase.NIGHT, ()),
        ("protect", "other_alive", None, Phase.NIGHT, ()),
        ("eliminate", "other_alive", None, Phase.NIGHT, ()),
        ("knowledge", "none", "allies", Phase.FINISHED, ()),
        ("death_reaction", "none", None, Phase.VOTING, ()),
        ("immunity", "none", None, Phase.NIGHT, ("attack",)),
        ("vulnerability", "none", None, Phase.NIGHT, ("inspect",)),
    ],
)
def test_supported_ability_components_are_role_independent(
    kind: str,
    target_policy: str,
    knowledge_mode: str | None,
    phase: Phase,
    source_kinds: tuple[str, ...],
) -> None:
    ability = AbilityDefinition(
        kind=kind,
        phase=phase,
        target_policy=target_policy,
        start_day=1,
        max_uses=None,
        result_visibility="none",
        resolution_priority=100,
        allow_repeat_target=True,
        enabled_first_night=True,
        result_detail="faction" if kind in {"inspect", "knowledge"} else None,
        knowledge_mode=knowledge_mode,
        tie_resolution="no_action" if kind == "attack" else None,
        source_kinds=source_kinds,
    )

    assert ability.kind == kind


@pytest.mark.parametrize(
    ("kind", "phase", "source_kinds"),
    [
        ("immunity", Phase.VOTING, ("attack",)),
        ("immunity", Phase.NIGHT, ("protect",)),
        ("vulnerability", Phase.NIGHT, ()),
        ("vulnerability", Phase.NIGHT, ("attack",)),
        ("death_reaction", Phase.DAY_DISCUSSION, ()),
    ],
)
def test_passive_ability_rejects_combinations_the_engine_cannot_resolve(
    kind: str,
    phase: Phase,
    source_kinds: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError):
        AbilityDefinition(
            kind=kind,
            phase=phase,
            target_policy="none",
            start_day=1,
            max_uses=None,
            result_visibility="none",
            resolution_priority=100,
            allow_repeat_target=True,
            enabled_first_night=True,
            result_detail=None,
            knowledge_mode=None,
            tie_resolution=None,
            source_kinds=source_kinds,
        )


def test_use_ability_envelope_requires_an_ability_id() -> None:
    option = AvailableAction(ActionType.USE_ABILITY, "custom_scan")
    action = Action.use_ability("p1", "custom_scan", "p2")

    assert option.key == "use_ability:custom_scan"
    assert action.ability_id == "custom_scan"

    with pytest.raises(ValueError, match="requires ability_id"):
        Action(type=ActionType.USE_ABILITY, player_id="p1", target_id="p2")
