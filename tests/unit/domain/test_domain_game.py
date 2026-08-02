from __future__ import annotations

import pytest

from werewolf_agent.domain import Action, ActionType, AvailableAction
from werewolf_agent.domain.state import (
    AbilityDefinition,
    DiscussionRelation,
    DiscussionRoundKind,
    DiscussionStageConfig,
    Phase,
    SubmissionMode,
)


def test_response_stage_rejects_independent_relation() -> None:
    """参照必須responseと矛盾するindependent定義をsetup境界で拒否する."""
    with pytest.raises(ValueError, match="cannot allow independent"):
        DiscussionStageConfig(
            stage=DiscussionRoundKind.RESPONSE,
            submission_mode=SubmissionMode.ORDERED,
            actor_order="reverse_opening",
            reference_stage=DiscussionRoundKind.OPENING,
            allowed_relations=(DiscussionRelation.INDEPENDENT,),
        )


@pytest.mark.parametrize(
    ("stage", "submission_mode", "actor_order", "reference_stage", "relations", "message"),
    [
        (
            DiscussionRoundKind.OPENING,
            SubmissionMode.ORDERED,
            "rotating",
            None,
            (DiscussionRelation.INDEPENDENT,),
            "opening stage must use sealed",
        ),
        (
            DiscussionRoundKind.OPENING,
            SubmissionMode.SEALED,
            "reverse_opening",
            None,
            (DiscussionRelation.INDEPENDENT,),
            "opening stage must use rotating actor order",
        ),
        (
            DiscussionRoundKind.RESPONSE,
            SubmissionMode.SEALED,
            "reverse_opening",
            DiscussionRoundKind.OPENING,
            (DiscussionRelation.SUPPORT,),
            "response stage must use ordered",
        ),
        (
            DiscussionRoundKind.RESPONSE,
            SubmissionMode.ORDERED,
            "rotating",
            DiscussionRoundKind.OPENING,
            (DiscussionRelation.SUPPORT,),
            "response stage must use reverse_opening actor order",
        ),
        (
            DiscussionRoundKind.RESPONSE,
            SubmissionMode.ORDERED,
            "reverse_opening",
            DiscussionRoundKind.OPENING,
            (DiscussionRelation.CHALLENGE,),
            "response stage must allow support",
        ),
    ],
)
def test_discussion_stage_rejects_unexecutable_protocols(
    stage: DiscussionRoundKind,
    submission_mode: SubmissionMode,
    actor_order: str,
    reference_stage: DiscussionRoundKind | None,
    relations: tuple[DiscussionRelation, ...],
    message: str,
) -> None:
    """Core policyが実行できないstage定義をsetup境界で拒否する."""
    with pytest.raises(ValueError, match=message):
        DiscussionStageConfig(
            stage=stage,
            submission_mode=submission_mode,
            actor_order=actor_order,
            reference_stage=reference_stage,
            allowed_relations=relations,
        )


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

    with pytest.raises(ValueError, match="ability_id"):
        Action.use_ability("p1", "", "p2")
