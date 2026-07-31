"""標準Evaluatorと決定的Experiment Reportの回帰テスト。"""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from werewolf_agent.agents import AgentSpec
from werewolf_agent.domain import RULE_PACK_CONTRACT_VERSION, RulePackManifest
from werewolf_agent.experiments import (
    ExperimentKind,
    PlayerAssignment,
    StandardEvaluator,
    TrialArtifactStore,
    TrialPlan,
    TrialPlayerResult,
    TrialResult,
    build_report,
)
from werewolf_agent.simulation import SimulationStopReason


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _plan(condition_id: str) -> TrialPlan:
    agent = AgentSpec("test", "1.0.0", _digest("agent"), {})
    return TrialPlan(
        trial_id=_digest(f"trial:{condition_id}"),
        pair_id=_digest("pair"),
        experiment_id="evaluation-test",
        experiment_fingerprint=_digest("experiment"),
        condition_id=condition_id,
        kind=ExperimentKind.AGENTS,
        seed=0,
        rotation_index=0,
        assignments=(
            PlayerAssignment("p1", "c1", "villager", "calm"),
            PlayerAssignment("p2", "c2", "werewolf", "bold"),
        ),
        setup_checksum=_digest("setup"),
        rule_pack=RulePackManifest(
            "core",
            RULE_PACK_CONTRACT_VERSION,
            "1.0.0",
            _digest("rules"),
        ),
        implementation_fingerprint=_digest(f"implementation:{condition_id}"),
        player_agent_specs={"p1": agent, "p2": agent},
    )


def _trace(
    *,
    action_type: str,
    ability_id: str | None,
    fallback: bool,
    latency_ms: int,
    diagnostics: dict[str, int],
) -> dict[str, object]:
    return {
        "decision_id": _digest(f"{action_type}:{fallback}"),
        "agent_spec": {},
        "response": {
            "action_type": action_type,
            "ability_id": ability_id,
            "target_id": "p2",
            "message": None,
            "focus_id": None,
            "evidence_id": None,
            "confidence": 0.8,
            "beliefs": {"p1": 0.2, "p2": 0.8},
            "intent": None,
            "metadata": {},
        },
        "latency_ms": latency_ms,
        "fallback_used": fallback,
        "error_code": "invalid_response" if fallback else None,
        "diagnostics": diagnostics,
    }


def _result(condition_id: str) -> TrialResult:
    return TrialResult(
        plan=_plan(condition_id),
        stop_reason=SimulationStopReason.FINISHED,
        winner_id="village",
        final_phase="finished",
        final_day=2,
        players=(
            TrialPlayerResult("p1", "c1", "villager", "village", "village", True, True),
            TrialPlayerResult(
                "p2",
                "c2",
                "werewolf",
                "werewolf",
                "werewolf",
                False,
                False,
            ),
        ),
        steps=(
            {
                "decision_trace": _trace(
                    action_type="vote",
                    ability_id=None,
                    fallback=False,
                    latency_ms=10,
                    diagnostics={"input_tokens": 3, "output_tokens": 2, "cost_micros": 7},
                )
            },
            {
                "decision_trace": _trace(
                    action_type="ability",
                    ability_id="inspect",
                    fallback=True,
                    latency_ms=30,
                    diagnostics={"input_tokens": 5, "output_tokens": 4, "cost_micros": 11},
                )
            },
        ),
        action_count=2,
        phase_count=3,
    )


def test_standard_evaluator_calculates_game_agent_and_operational_metrics() -> None:
    """LLM judgeなしで合法性、勝敗、対象、校正、利用量を集計する。"""
    metrics = StandardEvaluator(include_belief_calibration=True).evaluate((_result("baseline"),))

    assert metrics == {
        "trial_count": 1,
        "finished_trial_count": 1,
        "decision_count": 2,
        "legal_action_rate": 0.5,
        "fallback_rate": 0.5,
        "faction_win_rate": {"village": 1.0, "werewolf": 0.0},
        "survival_rate": {"village": 1.0, "werewolf": 0.0},
        "controller_win_rate": {"c1": 1.0, "c2": 0.0},
        "controller_survival_rate": {"c1": 1.0, "c2": 0.0},
        "role_win_rate": {"villager": 1.0, "werewolf": 0.0},
        "role_survival_rate": {"villager": 1.0, "werewolf": 0.0},
        "vote_targets": {"p2": 1},
        "vote_target_factions": {"werewolf": 1},
        "ability_targets": {"inspect": {"p2": 1}},
        "ability_target_factions": {"inspect": {"werewolf": 1}},
        "latency_ms": {"count": 2, "total": 40, "mean": 20.0, "max": 30},
        "tokens": {"sample_count": 2, "input": 8, "output": 6, "total": 14},
        "cost_micros": {"sample_count": 2, "total": 18},
        "belief_calibration": {"sample_count": 4, "brier_score": 0.04},
    }


def test_report_is_deterministic_and_regenerated_from_saved_trials(tmp_path: Path) -> None:
    """Artifact読込順に依存せず同じReport JSONを再生成する。"""
    store = TrialArtifactStore(tmp_path / "experiments")
    baseline = _result("baseline")
    candidate = _result("candidate")
    store.save(candidate)
    store.save(baseline)

    loaded = store.load_experiment("evaluation-test")
    first = build_report(
        loaded,
        (StandardEvaluator(include_belief_calibration=True),),
        expected_condition_ids=("baseline", "candidate"),
    )
    first_path = store.save_report(first)
    first_content = first_path.read_bytes()
    second = build_report(
        tuple(reversed(loaded)),
        (StandardEvaluator(include_belief_calibration=True),),
        expected_condition_ids=("baseline", "candidate"),
    )
    second_path = store.save_report(second)

    assert first.to_mapping() == second.to_mapping()
    assert first_content == second_path.read_bytes()
    assert first.paired_trial_count == 1
    assert [item.condition_id for item in first.conditions] == ["baseline", "candidate"]
    assert first.source_checksum == second.source_checksum


def test_standard_evaluator_counts_total_only_token_measurement() -> None:
    """total_tokensだけのprovider応答も計測済みとして集計する。"""
    result = _result("baseline")
    trace = _trace(
        action_type="vote",
        ability_id=None,
        fallback=False,
        latency_ms=10,
        diagnostics={"total_tokens": 9},
    )
    result = TrialResult(
        plan=result.plan,
        stop_reason=result.stop_reason,
        winner_id=result.winner_id,
        final_phase=result.final_phase,
        final_day=result.final_day,
        players=result.players,
        steps=({"decision_trace": trace},),
        action_count=1,
        phase_count=result.phase_count,
    )

    metrics = StandardEvaluator().evaluate((result,))

    assert metrics["tokens"] == {"sample_count": 1, "input": 0, "output": 0, "total": 9}


def test_partial_report_requires_all_planned_conditions_for_paired_count() -> None:
    """未実行conditionを含むpairは完了件数へ数えない。"""
    report = build_report(
        (_result("baseline"),),
        expected_condition_ids=("baseline", "candidate"),
    )

    assert report.paired_trial_count == 0


def test_report_rejects_trials_from_different_experiment_specifications() -> None:
    """同じIDでも仕様fingerprintが異なるTrialを集計しない。"""
    baseline = _result("baseline")
    candidate = _result("candidate")
    candidate = replace(
        candidate,
        plan=replace(candidate.plan, experiment_fingerprint=_digest("changed-experiment")),
    )

    with pytest.raises(ValueError, match="one experiment specification"):
        build_report(
            (baseline, candidate),
            expected_condition_ids=("baseline", "candidate"),
        )
