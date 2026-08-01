"""保存済みTrialだけから決定的な評価とReportを生成する。."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import isfinite
from types import MappingProxyType
from typing import Protocol

from werewolf_agent.experiments.contracts import EXPERIMENT_CONTRACT_VERSION
from werewolf_agent.experiments.execution import TrialResult
from werewolf_agent.setup import checksum_payload
from werewolf_agent.simulation import SimulationStopReason

STANDARD_EVALUATOR_VERSION = "0.4.0"


class Evaluator(Protocol):
    """Trial集合を一つの意味へ評価する外部注入契約。."""

    @property
    def evaluator_id(self) -> str:
        """安定したEvaluator IDを返す。."""
        ...

    @property
    def evaluator_version(self) -> str:
        """評価意味論のversionを返す。."""
        ...

    def evaluate(self, trials: Sequence[TrialResult]) -> Mapping[str, object]:
        """JSON互換の決定的なmetric mappingを返す。."""
        ...


@dataclass(frozen=True)
class EvaluationResult:
    """一つのEvaluatorが返したversion付きmetric集合。."""

    evaluator_id: str
    evaluator_version: str
    metrics: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """識別子とmetricをimmutableにする。."""
        object.__setattr__(self, "evaluator_id", _non_blank(self.evaluator_id, "evaluator_id"))
        object.__setattr__(
            self,
            "evaluator_version",
            _non_blank(self.evaluator_version, "evaluator_version"),
        )
        object.__setattr__(self, "metrics", _freeze_mapping(self.metrics))

    def to_mapping(self) -> dict[str, object]:
        """正規JSON表現を返す。."""
        return {
            "evaluator_id": self.evaluator_id,
            "evaluator_version": self.evaluator_version,
            "metrics": _json_value(self.metrics),
        }


class StandardEvaluator:
    """LLM judgeを使わない標準のゲーム・Agent評価。."""

    def __init__(self, *, include_belief_calibration: bool = False) -> None:
        """任意のwerewolf確率校正だけを切り替える。."""
        self._include_belief_calibration = include_belief_calibration

    @property
    def evaluator_id(self) -> str:
        """標準Evaluatorの安定IDを返す。."""
        return "standard"

    @property
    def evaluator_version(self) -> str:
        """標準評価意味論のversionを返す。."""
        return STANDARD_EVALUATOR_VERSION

    def evaluate(self, trials: Sequence[TrialResult]) -> Mapping[str, object]:
        """成功行動、勝敗、対象、運用値をTrialから集計する。."""
        items = tuple(trials)
        if not items:
            raise ValueError("trials must not be empty")
        decision_count = 0
        vote_targets: Counter[str] = Counter()
        vote_target_factions: Counter[str] = Counter()
        ability_targets: dict[str, Counter[str]] = defaultdict(Counter)
        ability_target_factions: dict[str, Counter[str]] = defaultdict(Counter)
        latency_values: list[int] = []
        token_totals = Counter[str]()
        cost_micros = 0
        token_sample_count = 0
        cost_sample_count = 0
        fallback_count = 0
        legal_count = 0
        belief_errors: list[float] = []

        for trial in items:
            players_by_id = {player.player_id: player for player in trial.players}
            true_werewolves = {
                player.player_id
                for player in trial.players
                if player.identity_faction_id == "werewolf"
            }
            for step in trial.steps:
                trace_value = step.get("decision_trace")
                if trace_value is None:
                    continue
                trace = _as_mapping(trace_value, "decision_trace")
                response_value = trace.get("response")
                response = (
                    None if response_value is None else _as_mapping(response_value, "response")
                )
                decision_count += 1
                fallback = _as_bool(trace.get("fallback_used"), "fallback_used")
                fallback_count += int(fallback)
                legal_count += int(
                    response is not None and not fallback and trace.get("error_code") is None
                )
                latency = _as_non_negative_int(trace.get("latency_ms"), "latency_ms")
                latency_values.append(latency)
                diagnostics = _as_mapping(trace.get("diagnostics", {}), "diagnostics")
                metadata = (
                    {}
                    if response is None
                    else _as_mapping(response.get("metadata", {}), "metadata")
                )
                input_tokens = _usage_int(diagnostics, metadata, "input_tokens")
                output_tokens = _usage_int(diagnostics, metadata, "output_tokens")
                total_tokens = _usage_int(diagnostics, metadata, "total_tokens")
                if (
                    input_tokens is not None
                    or output_tokens is not None
                    or total_tokens is not None
                ):
                    token_sample_count += 1
                    token_totals["input"] += input_tokens or 0
                    token_totals["output"] += output_tokens or 0
                    token_totals["total"] += (
                        total_tokens
                        if total_tokens is not None
                        else (input_tokens or 0) + (output_tokens or 0)
                    )
                cost = _usage_int(diagnostics, metadata, "cost_micros")
                if cost is not None:
                    cost_sample_count += 1
                    cost_micros += cost
                if response is None:
                    continue
                action_type = _as_text(response.get("action_type"), "action_type")
                target_id = _optional_text(response.get("target_id"), "target_id")
                ability_id = _optional_text(response.get("ability_id"), "ability_id")
                if action_type == "vote" and target_id is not None:
                    vote_targets[target_id] += 1
                    target = players_by_id.get(target_id)
                    if target is not None:
                        vote_target_factions[target.identity_faction_id] += 1
                if ability_id is not None and target_id is not None:
                    ability_targets[ability_id][target_id] += 1
                    target = players_by_id.get(target_id)
                    if target is not None:
                        ability_target_factions[ability_id][target.identity_faction_id] += 1
                if self._include_belief_calibration:
                    beliefs = _as_mapping(response.get("beliefs", {}), "beliefs")
                    for player_id, probability in beliefs.items():
                        belief = _as_probability(probability, f"beliefs.{player_id}")
                        truth = 1.0 if player_id in true_werewolves else 0.0
                        belief_errors.append((belief - truth) ** 2)

        faction_opportunities: Counter[str] = Counter()
        faction_wins: Counter[str] = Counter()
        survival_opportunities: Counter[str] = Counter()
        survival_counts: Counter[str] = Counter()
        controller_opportunities: Counter[str] = Counter()
        controller_wins: Counter[str] = Counter()
        controller_survival_opportunities: Counter[str] = Counter()
        controller_survivals: Counter[str] = Counter()
        role_opportunities: Counter[str] = Counter()
        role_wins: Counter[str] = Counter()
        role_survival_opportunities: Counter[str] = Counter()
        role_survivals: Counter[str] = Counter()
        for trial in items:
            finished = trial.stop_reason is SimulationStopReason.FINISHED
            if finished:
                factions = {player.victory_team_id for player in trial.players}
                for faction_id in factions:
                    faction_opportunities[faction_id] += 1
                    if trial.winner_id == faction_id:
                        faction_wins[faction_id] += 1
            for player in trial.players:
                survival_opportunities[player.identity_faction_id] += 1
                survival_counts[player.identity_faction_id] += int(player.alive)
                controller_survival_opportunities[player.controller_id] += 1
                controller_survivals[player.controller_id] += int(player.alive)
                role_survival_opportunities[player.role_id] += 1
                role_survivals[player.role_id] += int(player.alive)
                if finished:
                    controller_opportunities[player.controller_id] += 1
                    controller_wins[player.controller_id] += int(player.won)
                    role_opportunities[player.role_id] += 1
                    role_wins[player.role_id] += int(player.won)

        finished_trial_count = sum(
            item.stop_reason is SimulationStopReason.FINISHED for item in items
        )

        metrics: dict[str, object] = {
            "trial_count": len(items),
            "finished_trial_count": finished_trial_count,
            "incomplete_trial_count": len(items) - finished_trial_count,
            "decision_count": decision_count,
            "legal_action_rate": _rate(legal_count, decision_count),
            "fallback_rate": _rate(fallback_count, decision_count),
            "faction_win_rate": {
                key: _rate(faction_wins[key], count)
                for key, count in sorted(faction_opportunities.items())
            },
            "survival_rate": {
                key: _rate(survival_counts[key], count)
                for key, count in sorted(survival_opportunities.items())
            },
            "controller_win_rate": {
                key: _rate(controller_wins[key], count)
                for key, count in sorted(controller_opportunities.items())
            },
            "controller_survival_rate": {
                key: _rate(controller_survivals[key], count)
                for key, count in sorted(controller_survival_opportunities.items())
            },
            "role_win_rate": {
                key: _rate(role_wins[key], count)
                for key, count in sorted(role_opportunities.items())
            },
            "role_survival_rate": {
                key: _rate(role_survivals[key], count)
                for key, count in sorted(role_survival_opportunities.items())
            },
            "vote_targets": dict(sorted(vote_targets.items())),
            "vote_target_factions": dict(sorted(vote_target_factions.items())),
            "ability_targets": {
                ability_id: dict(sorted(targets.items()))
                for ability_id, targets in sorted(ability_targets.items())
            },
            "ability_target_factions": {
                ability_id: dict(sorted(targets.items()))
                for ability_id, targets in sorted(ability_target_factions.items())
            },
            "latency_ms": {
                "count": len(latency_values),
                "total": sum(latency_values),
                "mean": _mean(latency_values),
                "max": max(latency_values, default=0),
            },
            "tokens": {
                "sample_count": token_sample_count,
                "input": token_totals["input"],
                "output": token_totals["output"],
                "total": token_totals["total"],
            },
            "cost_micros": {"sample_count": cost_sample_count, "total": cost_micros},
        }
        if self._include_belief_calibration:
            metrics["belief_calibration"] = {
                "sample_count": len(belief_errors),
                "brier_score": _mean(belief_errors),
            }
        return metrics


@dataclass(frozen=True)
class ConditionReport:
    """一つの比較条件へ再生成した評価結果。."""

    condition_id: str
    trial_count: int
    evaluations: tuple[EvaluationResult, ...]

    def __post_init__(self) -> None:
        """条件ID、件数、Evaluatorの一意性を固定する。."""
        object.__setattr__(
            self,
            "condition_id",
            _non_blank(self.condition_id, "condition_id"),
        )
        if (
            not isinstance(self.trial_count, int)
            or isinstance(self.trial_count, bool)
            or self.trial_count < 1
        ):
            raise ValueError("trial_count must be positive")
        evaluations = tuple(self.evaluations)
        evaluator_ids = tuple(item.evaluator_id for item in evaluations)
        if not evaluations or len(evaluator_ids) != len(set(evaluator_ids)):
            raise ValueError("evaluations must have unique evaluator IDs")
        object.__setattr__(self, "evaluations", evaluations)

    def to_mapping(self) -> dict[str, object]:
        """正規JSON表現を返す。."""
        return {
            "condition_id": self.condition_id,
            "trial_count": self.trial_count,
            "evaluations": [item.to_mapping() for item in self.evaluations],
        }


@dataclass(frozen=True)
class ExperimentReport:
    """同じTrial artifactから再生成できる時刻非依存Report。."""

    experiment_id: str
    experiment_fingerprint: str
    source_checksum: str
    trial_ids: tuple[str, ...]
    paired_trial_count: int
    conditions: tuple[ConditionReport, ...]

    def __post_init__(self) -> None:
        """Source、Trial、Conditionの整合を検証して固定する。."""
        object.__setattr__(
            self,
            "experiment_id",
            _non_blank(self.experiment_id, "experiment_id"),
        )
        _require_sha256(self.experiment_fingerprint, "experiment_fingerprint")
        _require_sha256(self.source_checksum, "source_checksum")
        trial_ids = tuple(self.trial_ids)
        if not trial_ids or len(trial_ids) != len(set(trial_ids)):
            raise ValueError("trial_ids must be non-empty and unique")
        for trial_id in trial_ids:
            _require_sha256(trial_id, "trial_id")
        object.__setattr__(self, "trial_ids", trial_ids)
        conditions = tuple(self.conditions)
        condition_ids = tuple(item.condition_id for item in conditions)
        if not conditions or len(condition_ids) != len(set(condition_ids)):
            raise ValueError("conditions must be non-empty and unique")
        if sum(item.trial_count for item in conditions) != len(trial_ids):
            raise ValueError("condition trial counts must match trial_ids")
        if (
            not isinstance(self.paired_trial_count, int)
            or isinstance(self.paired_trial_count, bool)
            or not 0 <= self.paired_trial_count <= len(trial_ids)
        ):
            raise ValueError("paired_trial_count is outside the trial range")
        object.__setattr__(self, "conditions", conditions)

    def to_mapping(self) -> dict[str, object]:
        """正規JSON表現を返す。."""
        return {
            "contract_version": EXPERIMENT_CONTRACT_VERSION,
            "experiment_id": self.experiment_id,
            "experiment_fingerprint": self.experiment_fingerprint,
            "source_checksum": self.source_checksum,
            "trial_ids": list(self.trial_ids),
            "paired_trial_count": self.paired_trial_count,
            "conditions": [item.to_mapping() for item in self.conditions],
        }


def build_report(
    trials: Sequence[TrialResult],
    evaluators: Sequence[Evaluator] | None = None,
    *,
    expected_condition_ids: Sequence[str],
) -> ExperimentReport:
    """Trial内容と計画上の全条件からReportを決定的に生成する。."""
    items = tuple(sorted(trials, key=lambda item: item.plan.trial_id))
    if not items:
        raise ValueError("trials must not be empty")
    experiment_ids = {item.plan.experiment_id for item in items}
    if len(experiment_ids) != 1:
        raise ValueError("trials must belong to one experiment")
    experiment_fingerprints = {item.plan.experiment_fingerprint for item in items}
    if len(experiment_fingerprints) != 1:
        raise ValueError("trials must belong to one experiment specification")
    trial_ids = tuple(item.plan.trial_id for item in items)
    if len(trial_ids) != len(set(trial_ids)):
        raise ValueError("trials must contain unique trial IDs")
    selected = (StandardEvaluator(),) if evaluators is None else tuple(evaluators)
    evaluator_ids = tuple(item.evaluator_id for item in selected)
    if not selected or len(evaluator_ids) != len(set(evaluator_ids)):
        raise ValueError("evaluators must have unique IDs")
    selected = tuple(sorted(selected, key=lambda item: item.evaluator_id))

    condition_ids = tuple(expected_condition_ids)
    expected_conditions = {
        _non_blank(condition_id, "expected_condition_id") for condition_id in condition_ids
    }
    if not expected_conditions or len(expected_conditions) != len(condition_ids):
        raise ValueError("expected_condition_ids must be non-empty and unique")

    grouped: dict[str, list[TrialResult]] = defaultdict(list)
    paired: dict[str, set[str]] = defaultdict(set)
    for item in items:
        grouped[item.plan.condition_id].append(item)
        paired[item.plan.pair_id].add(item.plan.condition_id)
    unexpected_conditions = set(grouped) - expected_conditions
    if unexpected_conditions:
        raise ValueError("trials contain conditions outside expected_condition_ids")
    condition_reports = tuple(
        ConditionReport(
            condition_id,
            len(condition_trials),
            tuple(
                EvaluationResult(
                    evaluator.evaluator_id,
                    evaluator.evaluator_version,
                    evaluator.evaluate(condition_trials),
                )
                for evaluator in selected
            ),
        )
        for condition_id, condition_trials in sorted(grouped.items())
    )
    return ExperimentReport(
        experiment_id=next(iter(experiment_ids)),
        experiment_fingerprint=next(iter(experiment_fingerprints)),
        source_checksum=checksum_payload([item.to_mapping() for item in items]),
        trial_ids=trial_ids,
        paired_trial_count=sum(conditions == expected_conditions for conditions in paired.values()),
        conditions=condition_reports,
    )


def _rate(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 12)


def _mean(values: Sequence[int] | Sequence[float]) -> float | None:
    return None if not values else round(sum(values) / len(values), 12)


def _usage_int(
    diagnostics: Mapping[str, object],
    metadata: Mapping[str, object],
    key: str,
) -> int | None:
    if key in diagnostics:
        return _as_non_negative_int(diagnostics[key], f"diagnostics.{key}")
    if key in metadata:
        return _as_non_negative_int(metadata[key], f"metadata.{key}")
    return None


def _as_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return value


def _as_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-blank string")
    return value


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _as_text(value, field_name)


def _as_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _as_non_negative_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _as_probability(value: object, field_name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric")
    result = float(value)
    if not 0 <= result <= 1:
        raise ValueError(f"{field_name} must be between zero and one")
    return result


def _non_blank(value: object, field_name: str) -> str:
    return _as_text(value, field_name)


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    if any(not isinstance(key, str) or not key for key in value):
        raise ValueError("metric mapping keys must be non-blank strings")
    return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float) and isfinite(value):
        return value
    raise ValueError("metrics must contain finite JSON-compatible values")


def _json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


__all__ = [
    "STANDARD_EVALUATOR_VERSION",
    "ConditionReport",
    "EvaluationResult",
    "Evaluator",
    "ExperimentReport",
    "StandardEvaluator",
    "build_report",
]
