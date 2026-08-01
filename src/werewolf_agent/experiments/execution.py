"""Trialの逐次実行、atomic artifact、resumeを提供する。."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol

from werewolf_agent.agents import AgentSpec, DecisionResponse, DecisionTrace
from werewolf_agent.domain import GameEvent, RulePackManifest
from werewolf_agent.experiments.contracts import (
    EXPERIMENT_CONTRACT_VERSION,
    ExperimentKind,
    PlayerAssignment,
    TrialPlan,
)
from werewolf_agent.setup import checksum_payload
from werewolf_agent.simulation import (
    SimulationResult,
    SimulationSession,
    SimulationStep,
    SimulationStopReason,
)

if TYPE_CHECKING:
    from werewolf_agent.experiments.evaluation import ExperimentReport


class TrialSessionFactory(Protocol):
    """外部依存を組み立てて一試行のSimulationを返す境界。."""

    def create(self, plan: TrialPlan) -> SimulationSession:
        """Trial計画へ一致する未実行Sessionを返す。."""
        ...


@dataclass(frozen=True)
class TrialPlayerResult:
    """評価に必要な一人の最終状態と秘匿属性。."""

    player_id: str
    controller_id: str
    role_id: str
    identity_faction_id: str
    victory_team_id: str
    alive: bool
    won: bool

    def to_mapping(self) -> dict[str, object]:
        """JSON互換表現を返す。."""
        return {
            "player_id": self.player_id,
            "controller_id": self.controller_id,
            "role_id": self.role_id,
            "identity_faction_id": self.identity_faction_id,
            "victory_team_id": self.victory_team_id,
            "alive": self.alive,
            "won": self.won,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> TrialPlayerResult:
        """検証済みartifact値を復元する。."""
        return cls(
            _text(value, "player_id"),
            _text(value, "controller_id"),
            _text(value, "role_id"),
            _text(value, "identity_faction_id"),
            _text(value, "victory_team_id"),
            _boolean(value, "alive"),
            _boolean(value, "won"),
        )


@dataclass(frozen=True)
class TrialResult:
    """保存と再評価に使う一試行の完全な正規結果。."""

    plan: TrialPlan
    stop_reason: SimulationStopReason
    winner_id: str | None
    final_phase: str
    final_day: int
    players: tuple[TrialPlayerResult, ...]
    steps: tuple[Mapping[str, object], ...]
    action_count: int
    phase_count: int

    def __post_init__(self) -> None:
        """Collectionとenumをimmutableに固定する。."""
        object.__setattr__(self, "stop_reason", SimulationStopReason(self.stop_reason))
        object.__setattr__(self, "players", tuple(self.players))
        object.__setattr__(
            self,
            "steps",
            tuple(_freeze_mapping(value) for value in self.steps),
        )

    @classmethod
    def from_simulation(cls, plan: TrialPlan, result: SimulationResult) -> TrialResult:
        """Simulation結果を再評価可能なTrial結果へ変換する。."""
        if result.simulation_id != plan.trial_id:
            raise ValueError("simulation_id must match trial_id")
        state = result.state
        assignments = {item.player_id: item for item in plan.assignments}
        if set(assignments) != set(state.players):
            raise ValueError("simulation players must match trial assignments")
        players = tuple(
            TrialPlayerResult(
                player_id=player_id,
                controller_id=assignments[player_id].controller_id,
                role_id=_required_role(player.role, player_id),
                identity_faction_id=state.config.roles.faction_for_role(
                    _required_role(player.role, player_id)
                ),
                victory_team_id=state.config.roles.victory_team_for_role(
                    _required_role(player.role, player_id)
                ),
                alive=player.is_alive,
                won=(
                    state.win_result is not None
                    and player_id in state.win_result.winning_player_ids
                ),
            )
            for player_id, player in state.players.items()
        )
        if tuple(item.role_id for item in players) != tuple(
            assignments[item.player_id].role_id for item in players
        ):
            raise ValueError("simulation roles must match trial assignments")
        return cls(
            plan=plan,
            stop_reason=result.stop_reason,
            winner_id=result.winner_id,
            final_phase=state.phase.value,
            final_day=state.day,
            players=players,
            steps=tuple(_step_mapping(step) for step in result.steps),
            action_count=result.action_count,
            phase_count=result.phase_count,
        )

    def to_mapping(self) -> dict[str, object]:
        """checksum対象となる正規JSON表現を返す。."""
        return {
            "contract_version": EXPERIMENT_CONTRACT_VERSION,
            "plan": self.plan.to_mapping(),
            "stop_reason": self.stop_reason.value,
            "winner_id": self.winner_id,
            "final_phase": self.final_phase,
            "final_day": self.final_day,
            "players": [item.to_mapping() for item in self.players],
            "steps": [_json_value(item) for item in self.steps],
            "action_count": self.action_count,
            "phase_count": self.phase_count,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> TrialResult:
        """保存済みJSONを公開契約へ復元する。."""
        if value.get("contract_version") != EXPERIMENT_CONTRACT_VERSION:
            raise ValueError("unsupported experiment contract version")
        plan = _trial_plan(_mapping(value, "plan"))
        return cls(
            plan=plan,
            stop_reason=SimulationStopReason(_text(value, "stop_reason")),
            winner_id=_optional_text(value, "winner_id"),
            final_phase=_text(value, "final_phase"),
            final_day=_integer(value, "final_day"),
            players=tuple(
                TrialPlayerResult.from_mapping(_as_mapping(item, "player"))
                for item in _sequence(value, "players")
            ),
            steps=tuple(_as_mapping(item, "step") for item in _sequence(value, "steps")),
            action_count=_integer(value, "action_count", minimum=0),
            phase_count=_integer(value, "phase_count", minimum=0),
        )


@dataclass(frozen=True)
class TrialRunSummary:
    """一回のRunner呼出しで再利用・新規実行・保留となったTrial。."""

    results: tuple[TrialResult, ...]
    executed_trial_ids: tuple[str, ...]
    resumed_trial_ids: tuple[str, ...]
    remaining_trial_ids: tuple[str, ...]


class TrialArtifactStore:
    """Experiment配下のimmutable Trial JSONを所有するfile store。."""

    def __init__(self, root: Path) -> None:
        """Artifact rootを絶対pathへ固定する。."""
        self._root = root.resolve()

    @classmethod
    def default(cls, project_root: Path | None = None) -> TrialArtifactStore:
        """既定のrepository-local artifact rootを返す。."""
        root = (project_root or Path.cwd()).resolve()
        return cls(root / ".werewolf-agent" / "experiments")

    def load(self, plan: TrialPlan) -> TrialResult | None:
        """一致する完成済みTrialだけを返す。."""
        path = self._trial_path(plan)
        self._verify_experiment_binding(plan, required=path.is_file())
        if not path.is_file():
            return None
        result = self._load_path(path)
        if result.plan.to_mapping() != plan.to_mapping():
            raise ValueError(f"trial artifact plan mismatch: {path}")
        return result

    def load_experiment(self, experiment_id: str) -> tuple[TrialResult, ...]:
        """一つのexperimentに保存された全TrialをID順で返す。."""
        directory = self._experiment_path(experiment_id) / "trials"
        if not directory.is_dir():
            return ()
        results = tuple(self._load_path(path) for path in sorted(directory.glob("*.json")))
        if any(item.plan.experiment_id != experiment_id for item in results):
            raise ValueError("trial artifact belongs to a different experiment")
        fingerprints = {item.plan.experiment_fingerprint for item in results}
        if len(fingerprints) > 1:
            raise ValueError("experiment artifacts contain mixed experiment fingerprints")
        if results:
            self._verify_experiment_binding(results[0].plan, required=True)
        trial_ids = tuple(item.plan.trial_id for item in results)
        if len(trial_ids) != len(set(trial_ids)):
            raise ValueError("experiment artifacts contain duplicate trial IDs")
        return results

    def save_report(self, report: ExperimentReport) -> Path:
        """再生成可能なReport JSONを現在値としてatomic保存する。."""
        self._bind_experiment_identity(
            report.experiment_id,
            report.experiment_fingerprint,
        )
        path = self._experiment_path(report.experiment_id) / "report.json"
        content = (
            json.dumps(
                report.to_mapping(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_replace(path, content)
        return path

    def _load_path(self, path: Path) -> TrialResult:
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError(f"trial artifact must be an object: {path}")
        checksum = document.pop("artifact_checksum", None)
        if checksum != checksum_payload(document):
            raise ValueError(f"trial artifact checksum mismatch: {path}")
        result = TrialResult.from_mapping(document)
        if path.stem != result.plan.trial_id:
            raise ValueError(f"trial artifact filename does not match trial ID: {path}")
        return result

    def save(self, result: TrialResult) -> Path:
        """Trialを同一内容だけ再保存可能なatomic JSONとして保存する。."""
        self.bind_experiment(result.plan)
        path = self._trial_path(result.plan)
        document = result.to_mapping()
        document["artifact_checksum"] = checksum_payload(document)
        content = (
            json.dumps(
                document,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        )
        if path.is_file():
            if path.read_text(encoding="utf-8") != content:
                raise FileExistsError(f"immutable trial artifact already exists: {path}")
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{result.plan.trial_id}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        try:
            try:
                os.link(temporary_path, path)
            except FileExistsError:
                if path.read_text(encoding="utf-8") != content:
                    raise FileExistsError(
                        f"immutable trial artifact already exists: {path}"
                    ) from None
        finally:
            temporary_path.unlink(missing_ok=True)
        return path

    def bind_experiment(self, plan: TrialPlan) -> Path:
        """Experiment IDを一つのimmutableな仕様fingerprintへ固定する。."""
        return self._bind_experiment_identity(
            plan.experiment_id,
            plan.experiment_fingerprint,
        )

    def _bind_experiment_identity(
        self,
        experiment_id: str,
        experiment_fingerprint: str,
    ) -> Path:
        path = self._experiment_path(experiment_id) / "experiment.json"
        content = (
            json.dumps(
                {
                    "contract_version": EXPERIMENT_CONTRACT_VERSION,
                    "experiment_id": experiment_id,
                    "experiment_fingerprint": experiment_fingerprint,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        if path.is_file():
            if path.read_text(encoding="utf-8") != content:
                raise ValueError("experiment ID is already bound to a different specification")
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=".experiment.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        try:
            try:
                os.link(temporary_path, path)
            except FileExistsError:
                if path.read_text(encoding="utf-8") != content:
                    raise ValueError(
                        "experiment ID is already bound to a different specification"
                    ) from None
        finally:
            temporary_path.unlink(missing_ok=True)
        return path

    def _verify_experiment_binding(self, plan: TrialPlan, *, required: bool) -> None:
        path = self._experiment_path(plan.experiment_id) / "experiment.json"
        if not path.is_file():
            if required:
                raise ValueError("experiment binding is missing")
            return
        expected = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(expected, dict) or expected != {
            "contract_version": EXPERIMENT_CONTRACT_VERSION,
            "experiment_id": plan.experiment_id,
            "experiment_fingerprint": plan.experiment_fingerprint,
        }:
            raise ValueError("experiment ID is bound to a different specification")

    def _trial_path(self, plan: TrialPlan) -> Path:
        path = self._experiment_path(plan.experiment_id) / "trials" / f"{plan.trial_id}.json"
        resolved = path.resolve()
        if self._root != resolved and self._root not in resolved.parents:
            raise ValueError("experiment artifact path escapes its root")
        return resolved

    def _experiment_path(self, experiment_id: str) -> Path:
        path = (self._root / experiment_id).resolve()
        if self._root != path and self._root not in path.parents:
            raise ValueError("experiment artifact path escapes its root")
        return path


class TrialRunner:
    """Trial計画をSimulationへ委譲しcheckpointしながら逐次実行する。."""

    def __init__(self, factory: TrialSessionFactory, store: TrialArtifactStore) -> None:
        """実行compositionと保存先を注入する。."""
        self._factory = factory
        self._store = store

    def run(
        self,
        plans: Sequence[TrialPlan],
        *,
        max_new_trials: int | None = None,
    ) -> TrialRunSummary:
        """完成済みTrialを再利用し、指定件数まで新規実行する。."""
        if max_new_trials is not None and max_new_trials < 0:
            raise ValueError("max_new_trials must be non-negative")
        trial_ids = tuple(plan.trial_id for plan in plans)
        if len(trial_ids) != len(set(trial_ids)):
            raise ValueError("plans must contain unique trial IDs")
        experiment_keys = {(plan.experiment_id, plan.experiment_fingerprint) for plan in plans}
        if len(experiment_keys) > 1:
            raise ValueError("plans must belong to one experiment specification")
        results: list[TrialResult] = []
        executed: list[str] = []
        resumed: list[str] = []
        remaining: list[str] = []
        new_count = 0
        for plan in plans:
            cached = self._store.load(plan)
            if cached is not None:
                results.append(cached)
                resumed.append(plan.trial_id)
                continue
            if max_new_trials is not None and new_count >= max_new_trials:
                remaining.append(plan.trial_id)
                continue
            session = self._factory.create(plan)
            try:
                _validate_session(plan, session)
                self._store.bind_experiment(plan)
                result = TrialResult.from_simulation(plan, session.run())
            finally:
                session.close()
            self._store.save(result)
            results.append(result)
            executed.append(plan.trial_id)
            new_count += 1
        return TrialRunSummary(
            tuple(results),
            tuple(executed),
            tuple(resumed),
            tuple(remaining),
        )


def _validate_session(plan: TrialPlan, session: SimulationSession) -> None:
    if session.spec.simulation_id != plan.trial_id:
        raise ValueError("session simulation_id must match trial_id")
    if session.spec.seed != plan.seed:
        raise ValueError("session seed must match trial seed")
    if session.game.rule_pack_manifest != plan.rule_pack:
        raise ValueError("session Rule Pack must match trial plan")
    assignments = {item.player_id: item for item in plan.assignments}
    if set(session.spec.controllers) != set(assignments):
        raise ValueError("session controllers must match trial players")
    state = session.game.snapshot()
    if set(state.players) != set(assignments):
        raise ValueError("session players must match trial assignments")
    for player_id, assignment in assignments.items():
        controller = session.spec.controllers[player_id]
        if controller.factory is None:
            raise ValueError("experiment trials require Agent controllers")
        expected = plan.player_agent_specs[player_id]
        if controller.factory.spec != expected:
            raise ValueError("session Agent spec must match trial plan")
        if state.players[player_id].role != assignment.role_id:
            raise ValueError("session role assignment must match trial plan")


def _step_mapping(step: SimulationStep) -> dict[str, object]:
    return {
        "index": step.index,
        "kind": step.kind.value,
        "phase_before": step.phase_before,
        "phase_after": step.phase_after,
        "day_before": step.day_before,
        "day_after": step.day_after,
        "events": [_event_mapping(item) for item in step.events],
        "actor_id": step.actor_id,
        "action_type": step.action_type,
        "decision_trace": (
            None if step.decision_trace is None else _trace_mapping(step.decision_trace)
        ),
        "stop_reason": None if step.stop_reason is None else step.stop_reason.value,
    }


def _atomic_replace(path: Path, content: str) -> None:
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(content)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _event_mapping(event: GameEvent) -> dict[str, object]:
    return {
        "event_type": event.event_type,
        "phase": None if event.phase is None else event.phase.value,
        "day": event.day,
        "actor_id": event.actor_id,
        "visibility": event.visibility.value,
        "payload": _json_value(event.payload),
    }


def _trace_mapping(trace: DecisionTrace) -> dict[str, object]:
    return {
        "decision_id": trace.decision_id,
        "agent_spec": _agent_spec_mapping(trace.agent_spec),
        "response": None if trace.response is None else _response_mapping(trace.response),
        "latency_ms": trace.latency_ms,
        "fallback_used": trace.fallback_used,
        "error_code": trace.error_code,
        "diagnostics": _json_value(trace.diagnostics),
    }


def _response_mapping(response: DecisionResponse) -> dict[str, object]:
    return {
        "action_type": response.action_type,
        "ability_id": response.ability_id,
        "target_id": response.target_id,
        "utterance": response.utterance,
        "topic_id": response.topic_id,
        "position": response.position,
        "relation": response.relation,
        "evidence_id": response.evidence_id,
        "confidence": response.confidence,
        "beliefs": dict(response.beliefs),
        "intent": response.intent,
        "metadata": _json_value(response.metadata),
    }


def _trial_plan(value: Mapping[str, object]) -> TrialPlan:
    return TrialPlan(
        trial_id=_text(value, "trial_id"),
        pair_id=_text(value, "pair_id"),
        experiment_id=_text(value, "experiment_id"),
        experiment_fingerprint=_text(value, "experiment_fingerprint"),
        condition_id=_text(value, "condition_id"),
        kind=ExperimentKind(_text(value, "kind")),
        seed=_integer(value, "seed", minimum=None),
        rotation_index=_integer(value, "rotation_index", minimum=0),
        assignments=tuple(
            PlayerAssignment(**_string_mapping(_as_mapping(item, "assignment")))
            for item in _sequence(value, "assignments")
        ),
        setup_checksum=_text(value, "setup_checksum"),
        rule_pack=RulePackManifest.from_mapping(_mapping(value, "rule_pack")),
        implementation_fingerprint=_text(value, "implementation_fingerprint"),
        player_agent_specs={
            key: _agent_spec(_as_mapping(item, "agent_spec"))
            for key, item in _mapping(value, "player_agent_specs").items()
        },
    )


def _agent_spec(value: Mapping[str, object]) -> AgentSpec:
    return AgentSpec(
        _text(value, "agent_id"),
        _text(value, "implementation_version"),
        _text(value, "fingerprint"),
        _mapping(value, "parameters"),
    )


def _agent_spec_mapping(value: AgentSpec) -> dict[str, object]:
    return {
        "agent_id": value.agent_id,
        "implementation_version": value.implementation_version,
        "fingerprint": value.fingerprint,
        "parameters": _json_value(value.parameters),
    }


def _json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    return value


def _mapping(value: Mapping[str, object], key: str) -> Mapping[str, object]:
    return _as_mapping(value.get(key), key)


def _as_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return value


def _sequence(value: Mapping[str, object], key: str) -> Sequence[object]:
    item = value.get(key)
    if not isinstance(item, list):
        raise ValueError(f"{key} must be an array")
    return item


def _text(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{key} must be a non-blank string")
    return item


def _optional_text(value: Mapping[str, object], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{key} must be null or a non-blank string")
    return item


def _integer(
    value: Mapping[str, object],
    key: str,
    *,
    minimum: int | None = 1,
) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise ValueError(f"{key} must be an integer")
    if minimum is not None and item < minimum:
        raise ValueError(f"{key} must be greater than or equal to {minimum}")
    return item


def _boolean(value: Mapping[str, object], key: str) -> bool:
    item = value.get(key)
    if not isinstance(item, bool):
        raise ValueError(f"{key} must be a boolean")
    return item


def _string_mapping(value: Mapping[str, object]) -> dict[str, str]:
    return {key: _text(value, key) for key in value}


def _required_role(role: str | None, player_id: str) -> str:
    if role is None:
        raise ValueError(f"simulation player has no assigned role: {player_id}")
    return role


__all__ = [
    "TrialArtifactStore",
    "TrialPlayerResult",
    "TrialResult",
    "TrialRunSummary",
    "TrialRunner",
    "TrialSessionFactory",
]
