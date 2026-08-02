"""反復実験の条件、割当、試行計画を定義する標準ライブラリ契約。."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from werewolf_agent.agents import AgentSpec
from werewolf_agent.domain import RulePackManifest
from werewolf_agent.setup import checksum_payload

EXPERIMENT_CONTRACT_VERSION = "0.6.0"


class ExperimentKind(StrEnum):
    """比較対象となる責務境界。."""

    RULES = "rules"
    AGENTS = "agents"


class RotationMode(StrEnum):
    """試行ごとの割当rotation方式。."""

    NONE = "none"
    BALANCED = "balanced"


@dataclass(frozen=True)
class AgentBinding:
    """一つのcontrollerとpersonaへ固定Agent実装を結び付ける。."""

    controller_id: str
    persona_id: str
    agent_spec: AgentSpec

    def __post_init__(self) -> None:
        """Bindingの安定IDとAgent契約を検証する。."""
        object.__setattr__(
            self,
            "controller_id",
            _non_blank(self.controller_id, "controller_id"),
        )
        object.__setattr__(self, "persona_id", _non_blank(self.persona_id, "persona_id"))
        if not isinstance(self.agent_spec, AgentSpec):
            raise ValueError("agent_spec must be an AgentSpec")

    def to_mapping(self) -> dict[str, object]:
        """条件provenanceへ含める正規JSON表現を返す。."""
        return {
            "controller_id": self.controller_id,
            "persona_id": self.persona_id,
            "agent_spec": _agent_spec_mapping(self.agent_spec),
        }


@dataclass(frozen=True)
class RulesCondition:
    """一つのSetupとRule Packを比較する条件。."""

    condition_id: str
    setup_checksum: str
    rule_pack: RulePackManifest
    role_ids: tuple[str, ...]
    agent_bindings: tuple[AgentBinding, ...]

    def __post_init__(self) -> None:
        """再現に必要な識別子と役職multisetを検証する。."""
        object.__setattr__(self, "condition_id", _non_blank(self.condition_id, "condition_id"))
        object.__setattr__(
            self,
            "setup_checksum",
            _sha256(self.setup_checksum, "setup_checksum"),
        )
        object.__setattr__(self, "role_ids", _text_tuple(self.role_ids, "role_ids"))
        object.__setattr__(self, "agent_bindings", _agent_bindings(self.agent_bindings))

    @property
    def kind(self) -> ExperimentKind:
        """Rules比較条件であることを返す。."""
        return ExperimentKind.RULES

    def to_mapping(self) -> dict[str, object]:
        """Trial ID生成に使う正規JSON表現を返す。."""
        return {
            "condition_id": self.condition_id,
            "kind": self.kind.value,
            "setup_checksum": self.setup_checksum,
            "rule_pack": self.rule_pack.to_mapping(),
            "role_ids": list(self.role_ids),
            "agent_bindings": [item.to_mapping() for item in self.agent_bindings],
        }


@dataclass(frozen=True)
class AgentCondition:
    """同一ルール環境でcontroller別Agent実装を比較する条件。."""

    condition_id: str
    setup_checksum: str
    rule_pack: RulePackManifest
    role_ids: tuple[str, ...]
    agent_bindings: tuple[AgentBinding, ...]

    def __post_init__(self) -> None:
        """Controller IDとAgent provenanceを固定する。."""
        object.__setattr__(self, "condition_id", _non_blank(self.condition_id, "condition_id"))
        object.__setattr__(
            self,
            "setup_checksum",
            _sha256(self.setup_checksum, "setup_checksum"),
        )
        object.__setattr__(self, "role_ids", _text_tuple(self.role_ids, "role_ids"))
        object.__setattr__(self, "agent_bindings", _agent_bindings(self.agent_bindings))

    @property
    def kind(self) -> ExperimentKind:
        """Agent比較条件であることを返す。."""
        return ExperimentKind.AGENTS

    def to_mapping(self) -> dict[str, object]:
        """Trial ID生成に使う正規JSON表現を返す。."""
        return {
            "condition_id": self.condition_id,
            "kind": self.kind.value,
            "setup_checksum": self.setup_checksum,
            "rule_pack": self.rule_pack.to_mapping(),
            "role_ids": list(self.role_ids),
            "agent_bindings": [item.to_mapping() for item in self.agent_bindings],
        }


ExperimentCondition = RulesCondition | AgentCondition


@dataclass(frozen=True)
class ExperimentSpec:
    """比較条件、paired seed、割当対象を固定する実験仕様。."""

    experiment_id: str
    conditions: tuple[ExperimentCondition, ...]
    seeds: tuple[int, ...]
    player_ids: tuple[str, ...]
    controller_ids: tuple[str, ...]
    persona_ids: tuple[str, ...]
    rotation_mode: RotationMode = RotationMode.BALANCED

    def __post_init__(self) -> None:
        """比較可能性と割当の全単射を検証する。."""
        object.__setattr__(
            self,
            "experiment_id",
            _non_blank(self.experiment_id, "experiment_id"),
        )
        conditions = tuple(self.conditions)
        if len(conditions) < 2:
            raise ValueError("conditions must contain at least two comparison conditions")
        condition_ids = tuple(item.condition_id for item in conditions)
        _unique(condition_ids, "condition IDs")
        if len({item.kind for item in conditions}) != 1:
            raise ValueError("rules and agent conditions must not be mixed")
        object.__setattr__(self, "conditions", conditions)

        seeds = tuple(self.seeds)
        if not seeds:
            raise ValueError("seeds must not be empty")
        if any(not isinstance(seed, int) or isinstance(seed, bool) for seed in seeds):
            raise ValueError("seeds must contain integers")
        _unique(seeds, "seeds")
        object.__setattr__(self, "seeds", seeds)

        for field_name in ("player_ids", "controller_ids", "persona_ids"):
            values = _text_tuple(getattr(self, field_name), field_name)
            _unique(values, field_name)
            object.__setattr__(self, field_name, values)
        size = len(self.player_ids)
        if size < 1 or len(self.controller_ids) != size or len(self.persona_ids) != size:
            raise ValueError("player_ids, controller_ids, and persona_ids must have equal size")
        if any(len(item.role_ids) != size for item in conditions):
            raise ValueError("every condition must provide one role per player")
        if conditions[0].kind is ExperimentKind.AGENTS:
            self._validate_agent_conditions()
        else:
            self._validate_rules_conditions()
        object.__setattr__(self, "rotation_mode", RotationMode(self.rotation_mode))

    @property
    def kind(self) -> ExperimentKind:
        """この実験で比較する境界を返す。."""
        return self.conditions[0].kind

    def _validate_agent_conditions(self) -> None:
        conditions = tuple(item for item in self.conditions if isinstance(item, AgentCondition))
        first = conditions[0]
        environment = (first.setup_checksum, first.rule_pack, first.role_ids)
        if any(
            (item.setup_checksum, item.rule_pack, item.role_ids) != environment
            for item in conditions
        ):
            raise ValueError("agent conditions must share setup, rule pack, and roles")
        expected = {
            (controller_id, persona_id)
            for controller_id in self.controller_ids
            for persona_id in self.persona_ids
        }
        if any(_binding_keys(item.agent_bindings) != expected for item in conditions):
            raise ValueError("agent conditions must bind every controller and persona")

    def _validate_rules_conditions(self) -> None:
        conditions = tuple(item for item in self.conditions if isinstance(item, RulesCondition))
        expected = {
            (controller_id, persona_id)
            for controller_id in self.controller_ids
            for persona_id in self.persona_ids
        }
        if any(_binding_keys(item.agent_bindings) != expected for item in conditions):
            raise ValueError("rules conditions must bind every controller and persona")
        if any(item.agent_bindings != conditions[0].agent_bindings for item in conditions[1:]):
            raise ValueError("rules conditions must share fixed agent specifications")


@dataclass(frozen=True)
class PlayerAssignment:
    """一試行で一つのseatへ割り当てる比較要素。."""

    player_id: str
    controller_id: str
    role_id: str
    persona_id: str

    def __post_init__(self) -> None:
        """安定IDだけを受け付ける。."""
        for field_name in ("player_id", "controller_id", "role_id", "persona_id"):
            object.__setattr__(
                self,
                field_name,
                _non_blank(getattr(self, field_name), field_name),
            )

    def to_mapping(self) -> dict[str, str]:
        """正規JSON表現を返す。."""
        return {
            "player_id": self.player_id,
            "controller_id": self.controller_id,
            "role_id": self.role_id,
            "persona_id": self.persona_id,
        }


@dataclass(frozen=True)
class TrialPlan:
    """一回だけ実行するimmutableな試行計画。."""

    trial_id: str
    pair_id: str
    experiment_id: str
    experiment_fingerprint: str
    condition_id: str
    kind: ExperimentKind
    seed: int
    rotation_index: int
    assignments: tuple[PlayerAssignment, ...]
    setup_checksum: str
    rule_pack: RulePackManifest
    implementation_fingerprint: str
    player_agent_specs: Mapping[str, AgentSpec] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """永続化前に識別子と割当を固定する。."""
        for field_name in (
            "trial_id",
            "pair_id",
            "experiment_fingerprint",
            "implementation_fingerprint",
        ):
            object.__setattr__(self, field_name, _sha256(getattr(self, field_name), field_name))
        for field_name in ("experiment_id", "condition_id"):
            object.__setattr__(
                self,
                field_name,
                _non_blank(getattr(self, field_name), field_name),
            )
        object.__setattr__(self, "kind", ExperimentKind(self.kind))
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise ValueError("seed must be an integer")
        if not isinstance(self.rotation_index, int) or self.rotation_index < 0:
            raise ValueError("rotation_index must be a non-negative integer")
        assignments = tuple(self.assignments)
        if not assignments:
            raise ValueError("assignments must not be empty")
        _unique(tuple(item.player_id for item in assignments), "assigned player IDs")
        _unique(tuple(item.controller_id for item in assignments), "assigned controller IDs")
        _unique(tuple(item.persona_id for item in assignments), "assigned persona IDs")
        object.__setattr__(self, "assignments", assignments)
        object.__setattr__(
            self,
            "setup_checksum",
            _sha256(self.setup_checksum, "setup_checksum"),
        )
        agent_specs = _agent_specs(self.player_agent_specs)
        if set(agent_specs) != {item.player_id for item in assignments}:
            raise ValueError("player_agent_specs keys must match assigned player IDs")
        object.__setattr__(self, "player_agent_specs", agent_specs)

    def to_mapping(self) -> dict[str, object]:
        """artifactへ保存できる正規JSON表現を返す。."""
        return {
            "contract_version": EXPERIMENT_CONTRACT_VERSION,
            "trial_id": self.trial_id,
            "pair_id": self.pair_id,
            "experiment_id": self.experiment_id,
            "experiment_fingerprint": self.experiment_fingerprint,
            "condition_id": self.condition_id,
            "kind": self.kind.value,
            "seed": self.seed,
            "rotation_index": self.rotation_index,
            "assignments": [item.to_mapping() for item in self.assignments],
            "setup_checksum": self.setup_checksum,
            "rule_pack": self.rule_pack.to_mapping(),
            "implementation_fingerprint": self.implementation_fingerprint,
            "player_agent_specs": {
                key: _agent_spec_mapping(value)
                for key, value in sorted(self.player_agent_specs.items())
            },
        }


def plan_trials(spec: ExperimentSpec) -> tuple[TrialPlan, ...]:
    """条件をpaired seedと決定的な割当rotationへ展開する。."""
    rotations = _rotation_offsets(len(spec.player_ids), spec.rotation_mode)
    experiment_fingerprint = checksum_payload(_experiment_mapping(spec))
    plans: list[TrialPlan] = []
    for seed in spec.seeds:
        for rotation_index, offsets in enumerate(rotations):
            pair_payload = {
                "contract_version": EXPERIMENT_CONTRACT_VERSION,
                "experiment_id": spec.experiment_id,
                "experiment_fingerprint": experiment_fingerprint,
                "seed": seed,
                "rotation_index": rotation_index,
                "player_ids": list(spec.player_ids),
            }
            pair_id = checksum_payload(pair_payload)
            for condition in spec.conditions:
                assignments = _assign(spec, condition, offsets)
                implementation_fingerprint = checksum_payload(
                    _condition_implementation_mapping(condition)
                )
                identity = {
                    **pair_payload,
                    "condition": condition.to_mapping(),
                    "assignments": [item.to_mapping() for item in assignments],
                    "implementation_fingerprint": implementation_fingerprint,
                }
                plans.append(
                    TrialPlan(
                        trial_id=checksum_payload(identity),
                        pair_id=pair_id,
                        experiment_id=spec.experiment_id,
                        experiment_fingerprint=experiment_fingerprint,
                        condition_id=condition.condition_id,
                        kind=condition.kind,
                        seed=seed,
                        rotation_index=rotation_index,
                        assignments=assignments,
                        setup_checksum=condition.setup_checksum,
                        rule_pack=condition.rule_pack,
                        implementation_fingerprint=implementation_fingerprint,
                        player_agent_specs={
                            assignment.player_id: _binding_spec(condition, assignment)
                            for assignment in assignments
                        },
                    )
                )
    return tuple(plans)


def _rotation_offsets(size: int, mode: RotationMode) -> tuple[tuple[int, int, int], ...]:
    if mode is RotationMode.NONE:
        return ((0, 0, 0),)
    return tuple(
        (controller_offset, role_offset, (controller_offset + role_offset) % size)
        for controller_offset in range(size)
        for role_offset in range(size)
    )


def _assign(
    spec: ExperimentSpec,
    condition: ExperimentCondition,
    offsets: tuple[int, int, int],
) -> tuple[PlayerAssignment, ...]:
    controller_offset, role_offset, persona_offset = offsets
    size = len(spec.player_ids)
    return tuple(
        PlayerAssignment(
            player_id=player_id,
            controller_id=spec.controller_ids[(index + controller_offset) % size],
            role_id=condition.role_ids[(index + role_offset) % size],
            persona_id=spec.persona_ids[(index + persona_offset) % size],
        )
        for index, player_id in enumerate(spec.player_ids)
    )


def _agent_spec_mapping(value: AgentSpec) -> dict[str, object]:
    return {
        "agent_id": value.agent_id,
        "implementation_version": value.implementation_version,
        "fingerprint": value.fingerprint,
        "parameters": _json_value(value.parameters),
    }


def _agent_specs(values: Mapping[str, AgentSpec]) -> Mapping[str, AgentSpec]:
    agents = {_non_blank(key, "controller_id"): value for key, value in values.items()}
    if not agents:
        raise ValueError("agents must not be empty")
    if any(not isinstance(value, AgentSpec) for value in agents.values()):
        raise ValueError("agents must contain AgentSpec values")
    return MappingProxyType(dict(sorted(agents.items())))


def _agent_bindings(values: Sequence[AgentBinding]) -> tuple[AgentBinding, ...]:
    bindings = tuple(values)
    if not bindings or any(not isinstance(value, AgentBinding) for value in bindings):
        raise ValueError("agent_bindings must contain AgentBinding values")
    keys = tuple((item.controller_id, item.persona_id) for item in bindings)
    _unique(keys, "agent binding keys")
    return tuple(sorted(bindings, key=lambda item: (item.controller_id, item.persona_id)))


def _binding_keys(values: Sequence[AgentBinding]) -> set[tuple[str, str]]:
    return {(item.controller_id, item.persona_id) for item in values}


def _binding_spec(
    condition: ExperimentCondition,
    assignment: PlayerAssignment,
) -> AgentSpec:
    key = (assignment.controller_id, assignment.persona_id)
    return next(
        item.agent_spec
        for item in condition.agent_bindings
        if (item.controller_id, item.persona_id) == key
    )


def _json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


def _condition_implementation_mapping(
    condition: ExperimentCondition,
) -> dict[str, object]:
    mapping = condition.to_mapping()
    mapping.pop("condition_id")
    return mapping


def _experiment_mapping(spec: ExperimentSpec) -> dict[str, object]:
    return {
        "contract_version": EXPERIMENT_CONTRACT_VERSION,
        "experiment_id": spec.experiment_id,
        "conditions": [item.to_mapping() for item in spec.conditions],
        "seeds": list(spec.seeds),
        "player_ids": list(spec.player_ids),
        "controller_ids": list(spec.controller_ids),
        "persona_ids": list(spec.persona_ids),
        "rotation_mode": spec.rotation_mode.value,
    }


def _text_tuple(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    result = tuple(_non_blank(value, field_name) for value in values)
    if not result:
        raise ValueError(f"{field_name} must not be empty")
    return result


def _non_blank(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _sha256(value: object, field_name: str) -> str:
    normalized = _non_blank(value, field_name)
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return normalized


def _unique(values: Sequence[object], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must be unique")


__all__ = [
    "EXPERIMENT_CONTRACT_VERSION",
    "AgentBinding",
    "AgentCondition",
    "ExperimentCondition",
    "ExperimentKind",
    "ExperimentSpec",
    "PlayerAssignment",
    "RotationMode",
    "RulesCondition",
    "TrialPlan",
    "plan_trials",
]
