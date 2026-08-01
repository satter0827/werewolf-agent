"""Trial実行、artifact、resumeの回帰テスト。"""

from __future__ import annotations

import json
import random
from dataclasses import replace
from pathlib import Path

import pytest

from werewolf_agent.adapters.application_bridge import build_setup_catalog
from werewolf_agent.agents import HeuristicAgentFactory, RandomLegalAgentFactory
from werewolf_agent.domain import Game, GameSetup, Player, build_game_rules
from werewolf_agent.experiments import (
    AgentBinding,
    ExperimentSpec,
    RotationMode,
    RulesCondition,
    TrialArtifactStore,
    TrialPlan,
    TrialRunner,
    plan_trials,
)
from werewolf_agent.setup import namespace_seed, rule_definition_from_values
from werewolf_agent.simulation import (
    PlayerController,
    SimulationLimits,
    SimulationRunner,
    SimulationSession,
    SimulationSpec,
)


class _SessionFactory:
    def __init__(self, *, seed_offset: int = 0) -> None:
        catalog = build_setup_catalog()
        document = catalog.require_document(catalog.template_order[0])
        mechanics = document.mechanics
        self.rules = build_game_rules(
            rule_definition_from_values(
                player_count=sum(mechanics.role_counts.values()),
                role_counts=mechanics.role_counts,
                discussion=mechanics.discussion.to_mapping(),
                voting=mechanics.voting.to_mapping(),
                night=mechanics.night.to_mapping(),
                lifecycle=mechanics.lifecycle.to_mapping(),
                roles={key: value.to_mapping() for key, value in mechanics.roles.items()},
                abilities={key: value.to_mapping() for key, value in mechanics.abilities.items()},
            )
        )
        self.created: list[str] = []
        self.seed_offset = seed_offset

    def create(self, plan: TrialPlan) -> SimulationSession:
        self.created.append(plan.trial_id)
        game = Game.create(
            GameSetup(
                tuple(
                    Player(item.player_id, item.player_id, role=item.role_id)
                    for item in plan.assignments
                )
            ),
            rules=self.rules,
            random=random.Random(namespace_seed(plan.seed, "test:role-assignment")),
        )
        controllers = {
            item.player_id: PlayerController(item.player_id, RandomLegalAgentFactory())
            for item in plan.assignments
        }
        return SimulationRunner().start(
            game,
            SimulationSpec(
                plan.trial_id,
                plan.trial_id,
                plan.seed + self.seed_offset,
                controllers,
                SimulationLimits(max_actions=500, max_phases=50),
            ),
        )


def _plans(factory: _SessionFactory) -> tuple[TrialPlan, ...]:
    role_ids = tuple(
        role_id for role_id, count in factory.rules.config.role_counts.items() for _ in range(count)
    )
    player_ids = tuple(f"p{index}" for index in range(1, len(role_ids) + 1))
    controller_ids = tuple(f"c{index}" for index in range(1, len(role_ids) + 1))
    agent = RandomLegalAgentFactory().spec
    persona_ids = tuple(f"persona-{index}" for index in range(1, len(role_ids) + 1))
    agents = tuple(
        AgentBinding(controller_id, persona_id, agent)
        for controller_id in controller_ids
        for persona_id in persona_ids
    )
    conditions = tuple(
        RulesCondition(
            condition_id,
            "0" * 64,
            factory.rules.manifest,
            role_ids,
            agents,
        )
        for condition_id in ("baseline", "candidate")
    )
    return plan_trials(
        ExperimentSpec(
            "resume-test",
            conditions,
            (0,),
            player_ids,
            controller_ids,
            persona_ids,
            RotationMode.NONE,
        )
    )


def test_runner_checkpoints_each_trial_and_resumes_without_duplicate(tmp_path: Path) -> None:
    """中断後は完成済みTrialを読込み、残りだけを実行する。"""
    factory = _SessionFactory()
    plans = _plans(factory)
    store = TrialArtifactStore(tmp_path / "experiments")
    runner = TrialRunner(factory, store)

    first = runner.run(plans, max_new_trials=1)
    second = runner.run(plans)

    assert first.executed_trial_ids == (plans[0].trial_id,)
    assert first.resumed_trial_ids == ()
    assert first.remaining_trial_ids == (plans[1].trial_id,)
    assert second.executed_trial_ids == (plans[1].trial_id,)
    assert second.resumed_trial_ids == (plans[0].trial_id,)
    assert second.remaining_trial_ids == ()
    assert factory.created == [plans[0].trial_id, plans[1].trial_id]
    assert [item.plan.trial_id for item in second.results] == [
        plans[0].trial_id,
        plans[1].trial_id,
    ]
    assert all(item.players for item in second.results)
    assert all(item.steps for item in second.results)


def test_store_detects_tampering_and_plan_mismatch(tmp_path: Path) -> None:
    """Checksum破損と同じIDの異なる計画を再利用しない。"""
    factory = _SessionFactory()
    plan = _plans(factory)[0]
    store = TrialArtifactStore(tmp_path / "experiments")
    result = TrialRunner(factory, store).run((plan,)).results[0]
    path = store.save(result)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["winner_id"] = "tampered"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="checksum mismatch"):
        store.load(plan)


def test_runner_can_pause_without_creating_a_session(tmp_path: Path) -> None:
    """新規実行上限0は計画やartifactを変更しない。"""
    factory = _SessionFactory()
    plans = _plans(factory)

    summary = TrialRunner(factory, TrialArtifactStore(tmp_path)).run(
        plans,
        max_new_trials=0,
    )

    assert summary.results == ()
    assert summary.executed_trial_ids == ()
    assert summary.remaining_trial_ids == tuple(item.trial_id for item in plans)
    assert factory.created == []


def test_runner_loads_later_checkpoint_after_execution_limit(tmp_path: Path) -> None:
    """未完了Trialより後にある保存済みTrialもresume対象として認識する。"""
    factory = _SessionFactory()
    plans = _plans(factory)
    store = TrialArtifactStore(tmp_path)
    TrialRunner(factory, store).run((plans[1],))
    factory.created.clear()

    summary = TrialRunner(factory, store).run(plans, max_new_trials=0)

    assert summary.remaining_trial_ids == (plans[0].trial_id,)
    assert summary.resumed_trial_ids == (plans[1].trial_id,)
    assert [item.plan.trial_id for item in summary.results] == [plans[1].trial_id]
    assert factory.created == []


def test_runner_rejects_session_that_does_not_match_provenance(tmp_path: Path) -> None:
    """Factoryが異なるseedのSessionを返してもartifact化しない。"""
    factory = _SessionFactory(seed_offset=1)
    plan = _plans(factory)[0]

    with pytest.raises(ValueError, match="session seed must match"):
        TrialRunner(factory, TrialArtifactStore(tmp_path)).run((plan,))

    assert list(tmp_path.rglob("*.json")) == []


def test_runner_rejects_duplicate_trial_ids(tmp_path: Path) -> None:
    """同じTrialを一回のsummaryへ重複計上しない。"""
    factory = _SessionFactory()
    plan = _plans(factory)[0]

    with pytest.raises(ValueError, match="unique trial IDs"):
        TrialRunner(factory, TrialArtifactStore(tmp_path)).run((plan, plan))

    assert factory.created == []


def test_runner_rejects_agent_spec_for_a_different_persona(tmp_path: Path) -> None:
    """seatへ計画したpersonaと異なるAgent Factoryをartifact化しない。"""
    factory = _SessionFactory()
    plan = _plans(factory)[0]
    expected = dict(plan.player_agent_specs)
    expected[plan.assignments[0].player_id] = HeuristicAgentFactory().spec
    plan = replace(plan, player_agent_specs=expected)

    with pytest.raises(ValueError, match="Agent spec must match"):
        TrialRunner(factory, TrialArtifactStore(tmp_path)).run((plan,))

    assert list(tmp_path.rglob("*.json")) == []


def test_store_rejects_reusing_experiment_id_for_a_different_specification(
    tmp_path: Path,
) -> None:
    """同じexperiment IDへ異なる仕様世代のTrialを混在させない。"""
    factory = _SessionFactory()
    plan = _plans(factory)[0]
    runner = TrialRunner(factory, TrialArtifactStore(tmp_path))
    runner.run((plan,))
    created = list(factory.created)
    changed = replace(
        plan,
        trial_id="e" * 64,
        experiment_fingerprint="f" * 64,
    )

    with pytest.raises(ValueError, match="different specification"):
        runner.run((changed,))

    assert factory.created == created


def test_store_rejects_trial_without_experiment_binding(tmp_path: Path) -> None:
    """仕様bindingが欠落したTrialを暗黙復旧せず破損として拒否する。"""
    factory = _SessionFactory()
    plan = _plans(factory)[0]
    store = TrialArtifactStore(tmp_path)
    TrialRunner(factory, store).run((plan,))
    (tmp_path / plan.experiment_id / "experiment.json").unlink()

    with pytest.raises(ValueError, match="binding is missing"):
        store.load(plan)
