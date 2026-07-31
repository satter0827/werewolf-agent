"""反復可能なheadless比較実験の公開contractを提供する。."""

from werewolf_agent.experiments.contracts import (
    EXPERIMENT_CONTRACT_VERSION,
    AgentCondition,
    ExperimentCondition,
    ExperimentKind,
    ExperimentSpec,
    PlayerAssignment,
    RotationMode,
    RulesCondition,
    TrialPlan,
    plan_trials,
)
from werewolf_agent.experiments.evaluation import (
    STANDARD_EVALUATOR_VERSION,
    ConditionReport,
    EvaluationResult,
    Evaluator,
    ExperimentReport,
    StandardEvaluator,
    build_report,
)
from werewolf_agent.experiments.execution import (
    TrialArtifactStore,
    TrialPlayerResult,
    TrialResult,
    TrialRunner,
    TrialRunSummary,
    TrialSessionFactory,
)

__all__ = [
    "EXPERIMENT_CONTRACT_VERSION",
    "STANDARD_EVALUATOR_VERSION",
    "AgentCondition",
    "ConditionReport",
    "EvaluationResult",
    "Evaluator",
    "ExperimentCondition",
    "ExperimentKind",
    "ExperimentReport",
    "ExperimentSpec",
    "PlayerAssignment",
    "RotationMode",
    "RulesCondition",
    "StandardEvaluator",
    "TrialArtifactStore",
    "TrialPlan",
    "TrialPlayerResult",
    "TrialResult",
    "TrialRunSummary",
    "TrialRunner",
    "TrialSessionFactory",
    "build_report",
    "plan_trials",
]
