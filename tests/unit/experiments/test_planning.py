"""Experiment契約と決定的Trial計画の回帰テスト。"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from hashlib import sha256

import pytest

from werewolf_agent.agents import AgentSpec
from werewolf_agent.domain import (
    RULE_PACK_CONTRACT_VERSION,
    RulePackManifest,
)
from werewolf_agent.experiments import (
    AgentBinding,
    AgentCondition,
    ExperimentKind,
    ExperimentSpec,
    RotationMode,
    RulesCondition,
    plan_trials,
)


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _rule_pack(name: str = "core") -> RulePackManifest:
    return RulePackManifest(name, RULE_PACK_CONTRACT_VERSION, "1.0.0", _digest(name))


def _rules_condition(
    condition_id: str,
    roles: tuple[str, ...],
    persona_ids: tuple[str, ...] | None = None,
) -> RulesCondition:
    controller_ids = tuple(f"c{index}" for index in range(1, len(roles) + 1))
    selected_personas = persona_ids or ("calm", "bold", "careful")[: len(roles)]
    return RulesCondition(
        condition_id,
        _digest(f"setup:{condition_id}"),
        _rule_pack(condition_id),
        roles,
        _bindings(
            controller_ids,
            selected_personas,
            lambda controller_id, persona_id: _agent(f"fixed-{controller_id}-{persona_id}"),
        ),
    )


def _agent(agent_id: str) -> AgentSpec:
    return AgentSpec(agent_id, "1.0.0", _digest(agent_id), {"temperature": 0})


def _bindings(
    controller_ids: tuple[str, ...],
    persona_ids: tuple[str, ...],
    factory: Callable[[str, str], AgentSpec],
) -> tuple[AgentBinding, ...]:
    return tuple(
        AgentBinding(controller_id, persona_id, factory(controller_id, persona_id))
        for controller_id in controller_ids
        for persona_id in persona_ids
    )


def test_rules_plan_pairs_conditions_and_identifies_implementations() -> None:
    """同じseedとrotationはpairを共有し、条件は別trialになる。"""
    spec = ExperimentSpec(
        experiment_id="rules-comparison",
        conditions=(
            _rules_condition("baseline", ("villager", "seer", "werewolf")),
            _rules_condition("variant", ("villager", "seer", "werewolf")),
        ),
        seeds=(11,),
        player_ids=("p1", "p2", "p3"),
        controller_ids=("c1", "c2", "c3"),
        persona_ids=("calm", "bold", "careful"),
        rotation_mode=RotationMode.NONE,
    )

    first, second = plan_trials(spec)

    assert first.kind is ExperimentKind.RULES
    assert first.pair_id == second.pair_id
    assert first.trial_id != second.trial_id
    assert first.implementation_fingerprint != second.implementation_fingerprint
    assert set(first.player_agent_specs) == {"p1", "p2", "p3"}
    assert first.to_mapping()["contract_version"] == "0.6.0"


def test_balanced_rotation_removes_controller_role_and_persona_bias() -> None:
    """n² rotationで各controllerが各roleとpersonaへ同数割り当たる。"""
    spec = ExperimentSpec(
        experiment_id="balanced",
        conditions=(
            _rules_condition("a", ("villager", "seer", "werewolf")),
            _rules_condition("b", ("villager", "seer", "werewolf")),
        ),
        seeds=(7,),
        player_ids=("p1", "p2", "p3"),
        controller_ids=("c1", "c2", "c3"),
        persona_ids=("calm", "bold", "careful"),
    )

    plans = tuple(item for item in plan_trials(spec) if item.condition_id == "a")

    assert len(plans) == 9
    controller_roles = Counter(
        (item.controller_id, item.role_id) for plan in plans for item in plan.assignments
    )
    controller_personas = Counter(
        (item.controller_id, item.persona_id) for plan in plans for item in plan.assignments
    )
    assert set(controller_roles.values()) == {3}
    assert set(controller_personas.values()) == {3}
    for plan in plans:
        for assignment in plan.assignments:
            assert plan.player_agent_specs[assignment.player_id].agent_id == (
                f"fixed-{assignment.controller_id}-{assignment.persona_id}"
            )


def test_trial_plan_is_deterministic_and_changes_with_assignment_input() -> None:
    """同じSpecは同じID列になり、persona変更はtrialだけを変える。"""

    def build(persona_ids: tuple[str, ...]) -> ExperimentSpec:
        return ExperimentSpec(
            experiment_id="deterministic",
            conditions=(
                _rules_condition("a", ("villager", "werewolf"), persona_ids),
                _rules_condition("b", ("villager", "werewolf"), persona_ids),
            ),
            seeds=(3, 5),
            player_ids=("p1", "p2"),
            controller_ids=("c1", "c2"),
            persona_ids=persona_ids,
            rotation_mode=RotationMode.NONE,
        )

    original = build(("calm", "bold"))
    changed = build(("calm", "careful"))

    first = plan_trials(original)
    second = plan_trials(original)
    other = plan_trials(changed)

    assert [item.to_mapping() for item in first] == [item.to_mapping() for item in second]
    assert [item.pair_id for item in first] != [item.pair_id for item in other]
    assert [item.trial_id for item in first] != [item.trial_id for item in other]


def test_condition_label_is_not_part_of_implementation_fingerprint() -> None:
    """比較用labelと実装identityを混同しない。"""
    manifest = _rule_pack()
    setup_checksum = _digest("setup")
    roles = ("villager", "werewolf")
    fixed_agents = _bindings(
        ("c1", "c2"),
        ("calm", "bold"),
        lambda controller_id, persona_id: _agent(f"{controller_id}-{persona_id}"),
    )
    spec = ExperimentSpec(
        "labels",
        (
            RulesCondition("before", setup_checksum, manifest, roles, fixed_agents),
            RulesCondition("after", setup_checksum, manifest, roles, fixed_agents),
        ),
        (1,),
        ("p1", "p2"),
        ("c1", "c2"),
        ("calm", "bold"),
        RotationMode.NONE,
    )

    first, second = plan_trials(spec)

    assert first.implementation_fingerprint == second.implementation_fingerprint
    assert first.trial_id != second.trial_id


def test_nested_agent_parameters_are_json_compatible_in_trial_identity() -> None:
    """AgentSpecの再帰immutable値をhash可能なJSON表現へ戻す。"""
    nested = AgentSpec(
        "nested",
        "1.0.0",
        _digest("nested"),
        {"generation": {"temperature": 0, "stops": ["END"]}},
    )
    manifest = _rule_pack()
    setup_checksum = _digest("setup")
    roles = ("villager", "werewolf")
    condition_agents = _bindings(
        ("c1", "c2"),
        ("calm", "bold"),
        lambda controller_id, _persona_id: nested if controller_id == "c1" else _agent("fixed"),
    )
    spec = ExperimentSpec(
        "nested-parameters",
        (
            RulesCondition("before", setup_checksum, manifest, roles, condition_agents),
            RulesCondition("after", setup_checksum, manifest, roles, condition_agents),
        ),
        (1,),
        ("p1", "p2"),
        ("c1", "c2"),
        ("calm", "bold"),
        RotationMode.NONE,
    )

    plans = plan_trials(spec)

    assert plans[0].to_mapping()["player_agent_specs"] == {
        "p1": {
            "agent_id": "nested",
            "implementation_version": "1.0.0",
            "fingerprint": _digest("nested"),
            "parameters": {"generation": {"stops": ["END"], "temperature": 0}},
        },
        "p2": {
            "agent_id": "fixed",
            "implementation_version": "1.0.0",
            "fingerprint": _digest("fixed"),
            "parameters": {"temperature": 0},
        },
    }


def test_agent_conditions_share_environment_and_bind_every_controller() -> None:
    """Agent比較ではRule、Setup、役職を固定し全controllerを明示する。"""
    manifest = _rule_pack()
    checksum = _digest("setup")
    baseline = AgentCondition(
        "baseline",
        checksum,
        manifest,
        ("villager", "werewolf"),
        _bindings(
            ("c1", "c2"),
            ("calm", "bold"),
            lambda controller_id, persona_id: _agent(
                f"old-{persona_id}" if controller_id == "c1" else f"opponent-{persona_id}"
            ),
        ),
    )
    candidate = AgentCondition(
        "candidate",
        checksum,
        manifest,
        ("villager", "werewolf"),
        _bindings(
            ("c1", "c2"),
            ("calm", "bold"),
            lambda controller_id, persona_id: _agent(
                f"new-{persona_id}" if controller_id == "c1" else f"opponent-{persona_id}"
            ),
        ),
    )
    spec = ExperimentSpec(
        "agent-comparison",
        (baseline, candidate),
        (1,),
        ("p1", "p2"),
        ("c1", "c2"),
        ("calm", "bold"),
        RotationMode.NONE,
    )

    plans = plan_trials(spec)

    assert all(plan.kind is ExperimentKind.AGENTS for plan in plans)
    assert plans[0].player_agent_specs["p1"].agent_id == "old-calm"
    assert plans[1].player_agent_specs["p1"].agent_id == "new-calm"


def test_experiment_rejects_mixed_conditions_and_unpaired_agent_environment() -> None:
    """責務の混在と交絡するAgent比較を計画前に拒否する。"""
    rules = _rules_condition("rules", ("villager", "werewolf"))
    agents = AgentCondition(
        "agents",
        _digest("setup"),
        _rule_pack(),
        ("villager", "werewolf"),
        _bindings(
            ("c1", "c2"),
            ("calm", "bold"),
            lambda controller_id, persona_id: _agent(f"{controller_id}-{persona_id}"),
        ),
    )
    with pytest.raises(ValueError, match="must not be mixed"):
        ExperimentSpec(
            "invalid",
            (rules, agents),
            (1,),
            ("p1", "p2"),
            ("c1", "c2"),
            ("calm", "bold"),
        )

    changed_environment = AgentCondition(
        "changed",
        _digest("other-setup"),
        _rule_pack(),
        ("villager", "werewolf"),
        agents.agent_bindings,
    )
    with pytest.raises(ValueError, match="must share setup"):
        ExperimentSpec(
            "invalid",
            (agents, changed_environment),
            (1,),
            ("p1", "p2"),
            ("c1", "c2"),
            ("calm", "bold"),
        )


def test_rules_experiment_rejects_agent_changes_between_conditions() -> None:
    """Rules比較へAgent差分を混入させない。"""
    roles = ("villager", "werewolf")
    first = _rules_condition("first", roles)
    second = RulesCondition(
        "second",
        _digest("second"),
        _rule_pack("second"),
        roles,
        tuple(
            AgentBinding(
                item.controller_id,
                item.persona_id,
                _agent("changed") if item.controller_id == "c1" else item.agent_spec,
            )
            for item in first.agent_bindings
        ),
    )

    with pytest.raises(ValueError, match="must share fixed agent"):
        ExperimentSpec(
            "invalid-rules",
            (first, second),
            (1,),
            ("p1", "p2"),
            ("c1", "c2"),
            ("calm", "bold"),
        )


def test_experiment_rejects_missing_controller_persona_binding() -> None:
    """一つでも未定義のcontrollerとpersonaの組合せがあれば拒否する。"""
    roles = ("villager", "werewolf")
    first = _rules_condition("first", roles)
    incomplete = RulesCondition(
        "second",
        _digest("second"),
        _rule_pack("second"),
        roles,
        first.agent_bindings[:-1],
    )

    with pytest.raises(ValueError, match="bind every controller and persona"):
        ExperimentSpec(
            "incomplete-bindings",
            (first, incomplete),
            (1,),
            ("p1", "p2"),
            ("c1", "c2"),
            ("calm", "bold"),
        )
