"""一局のheadless実行に使う標準ライブラリ契約を定義する."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol

from werewolf_agent.agents import (
    AgentFactory,
    AgentIdentity,
    AgentSession,
    AgentWorld,
    DecisionRequest,
    DecisionResponse,
    DecisionTrace,
    HeuristicAgentFactory,
)
from werewolf_agent.domain import GameEvent, GameState, GameView

SIMULATION_CONTRACT_VERSION = "0.4.0"


class SimulationStepKind(StrEnum):
    """一つのSimulation stepが行った操作を表す."""

    AGENT_ACTION = "agent_action"
    MANUAL_ACTION = "manual_action"
    PHASE_ADVANCED = "phase_advanced"
    WAITING_FOR_MANUAL = "waiting_for_manual"
    FINISHED = "finished"
    LIMIT_REACHED = "limit_reached"
    CANCELLED = "cancelled"


class SimulationStopReason(StrEnum):
    """Simulationが継続しない理由を表す."""

    WAITING_FOR_MANUAL = "waiting_for_manual"
    FINISHED = "finished"
    ACTION_LIMIT = "action_limit"
    PHASE_LIMIT = "phase_limit"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class SimulationLimits:
    """一局の実行量とAgent待機時間の上限を定義する."""

    max_actions: int = 1_000
    max_phases: int = 100
    decision_timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        """正の有限上限だけを受け付ける."""
        _positive_integer(self.max_actions, "max_actions")
        _positive_integer(self.max_phases, "max_phases")
        if self.decision_timeout_seconds is not None:
            if not isinstance(self.decision_timeout_seconds, (int, float)) or isinstance(
                self.decision_timeout_seconds, bool
            ):
                raise ValueError("decision_timeout_seconds must be a number")
            value = float(self.decision_timeout_seconds)
            if value <= 0 or value == float("inf") or value != value:
                raise ValueError("decision_timeout_seconds must be positive and finite")
            object.__setattr__(self, "decision_timeout_seconds", value)


@dataclass(frozen=True)
class AgentMetadata:
    """一回の本人用observationへ付加する役職情報と世界設定."""

    identity: AgentIdentity | None = None
    world: AgentWorld | None = None


class AgentMetadataProvider(Protocol):
    """現在の本人用viewから動的なAgent metadataを解決する境界."""

    def resolve(self, observation: GameView) -> AgentMetadata:
        """他プレイヤーの秘匿情報を含まないmetadataを返す."""
        ...


@dataclass(frozen=True)
class PlayerController:
    """一人のプレイヤーへmanualまたはAgent制御を割り当てる."""

    player_id: str
    factory: AgentFactory | None = None
    identity: AgentIdentity | None = None
    world: AgentWorld | None = None
    metadata_provider: AgentMetadataProvider | None = None
    fallback_factory: AgentFactory = field(default_factory=HeuristicAgentFactory)

    def __post_init__(self) -> None:
        """プレイヤーIDを正規化する."""
        object.__setattr__(self, "player_id", _non_blank(self.player_id, "player_id"))

    @property
    def is_manual(self) -> bool:
        """外部入力を待つcontrollerか返す."""
        return self.factory is None


@dataclass(frozen=True)
class SimulationSpec:
    """一局の識別子、seed、controller、上限を固定する."""

    simulation_id: str
    game_id: str
    seed: int
    controllers: Mapping[str, PlayerController]
    limits: SimulationLimits = field(default_factory=SimulationLimits)
    phase_seed: int | None = None
    speech_message_max_chars: int | None = None

    def __post_init__(self) -> None:
        """Controller mappingをimmutableにして参照整合を検証する."""
        object.__setattr__(
            self,
            "simulation_id",
            _non_blank(self.simulation_id, "simulation_id"),
        )
        object.__setattr__(self, "game_id", _non_blank(self.game_id, "game_id"))
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise ValueError("seed must be an integer")
        if self.phase_seed is not None and (
            not isinstance(self.phase_seed, int) or isinstance(self.phase_seed, bool)
        ):
            raise ValueError("phase_seed must be an integer")
        if self.speech_message_max_chars is not None:
            _positive_integer(self.speech_message_max_chars, "speech_message_max_chars")
        controllers = dict(self.controllers)
        if not controllers:
            raise ValueError("controllers must not be empty")
        if any(key != controller.player_id for key, controller in controllers.items()):
            raise ValueError("controller keys must match player IDs")
        object.__setattr__(self, "controllers", MappingProxyType(controllers))


@dataclass(frozen=True)
class SimulationStep:
    """一回の状態変更または停止判定を表す."""

    index: int
    kind: SimulationStepKind
    phase_before: str
    phase_after: str
    day_before: int
    day_after: int
    events: tuple[GameEvent, ...] = ()
    actor_id: str | None = None
    action_type: str | None = None
    decision_trace: DecisionTrace | None = None
    stop_reason: SimulationStopReason | None = None

    def __post_init__(self) -> None:
        """stepの順序値とimmutable event列を検証する."""
        _positive_integer(self.index, "index")
        object.__setattr__(self, "kind", SimulationStepKind(self.kind))
        object.__setattr__(self, "events", tuple(self.events))
        object.__setattr__(
            self,
            "actor_id",
            None if self.actor_id is None else _non_blank(self.actor_id, "actor_id"),
        )
        object.__setattr__(
            self,
            "action_type",
            None if self.action_type is None else _non_blank(self.action_type, "action_type"),
        )
        if self.stop_reason is not None:
            object.__setattr__(self, "stop_reason", SimulationStopReason(self.stop_reason))
        terminal_kinds = {
            SimulationStepKind.WAITING_FOR_MANUAL,
            SimulationStepKind.FINISHED,
            SimulationStepKind.LIMIT_REACHED,
            SimulationStepKind.CANCELLED,
        }
        if (self.kind in terminal_kinds) != (self.stop_reason is not None):
            raise ValueError("terminal step kind and stop_reason must be present together")
        if self.kind in {SimulationStepKind.AGENT_ACTION, SimulationStepKind.MANUAL_ACTION} and (
            self.actor_id is None or self.action_type is None
        ):
            raise ValueError("action steps require actor_id and action_type")


@dataclass(frozen=True)
class SimulationResult:
    """停止時点の再利用可能な一局実行結果を表す."""

    simulation_id: str
    stop_reason: SimulationStopReason
    state: GameState
    steps: tuple[SimulationStep, ...]
    action_count: int
    phase_count: int

    def __post_init__(self) -> None:
        """結果collectionと件数を固定する."""
        object.__setattr__(
            self,
            "simulation_id",
            _non_blank(self.simulation_id, "simulation_id"),
        )
        object.__setattr__(self, "stop_reason", SimulationStopReason(self.stop_reason))
        object.__setattr__(self, "steps", tuple(self.steps))
        _non_negative_integer(self.action_count, "action_count")
        _non_negative_integer(self.phase_count, "phase_count")

    @property
    def winner_id(self) -> str | None:
        """終局済みなら正規winning faction IDを返す."""
        return self.state.winner_id


class DecisionExecutor(Protocol):
    """同期Agent呼出しのoperational policyを注入する境界."""

    def decide(
        self,
        session: AgentSession,
        request: DecisionRequest,
        *,
        timeout_seconds: float | None,
    ) -> DecisionResponse:
        """一回だけAgentを呼び出して応答する."""
        ...


class DecisionTraceSink(Protocol):
    """chain-of-thoughtを含まない意思決定traceの出力境界."""

    def record_decision(self, trace: DecisionTrace) -> None:
        """一回の意思決定traceを保存する."""
        ...


class NullDecisionTraceSink:
    """意思決定traceを破棄する既定sink."""

    def record_decision(self, trace: DecisionTrace) -> None:
        """何も保存しない."""
        _ = trace


def _non_blank(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _positive_integer(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")


def _non_negative_integer(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


__all__ = [
    "SIMULATION_CONTRACT_VERSION",
    "AgentMetadata",
    "AgentMetadataProvider",
    "DecisionExecutor",
    "DecisionTraceSink",
    "NullDecisionTraceSink",
    "PlayerController",
    "SimulationLimits",
    "SimulationResult",
    "SimulationSpec",
    "SimulationStep",
    "SimulationStepKind",
    "SimulationStopReason",
]
