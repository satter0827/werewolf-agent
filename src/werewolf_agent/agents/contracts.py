"""外部Agentを同期Sessionとして注入する標準ライブラリ契約を定義する."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from werewolf_agent.agents.validation import non_blank, optional_non_blank

AGENT_CONTRACT_VERSION = "0.2.0"


@dataclass(frozen=True)
class AgentSpec:
    """Agent実装と固定parameterを再現可能に識別する."""

    agent_id: str
    implementation_version: str
    fingerprint: str
    parameters: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """IdentityとJSON互換parameterを正規化する."""
        object.__setattr__(self, "agent_id", non_blank(self.agent_id, "agent_id"))
        object.__setattr__(
            self,
            "implementation_version",
            non_blank(self.implementation_version, "implementation_version"),
        )
        object.__setattr__(self, "fingerprint", non_blank(self.fingerprint, "fingerprint"))
        if len(self.fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in self.fingerprint
        ):
            raise ValueError("fingerprint must be a lowercase SHA-256 digest")
        object.__setattr__(self, "parameters", _freeze_mapping(self.parameters))


@dataclass(frozen=True)
class AgentContext:
    """一つのgameとplayerへ分離したAgent Sessionの作成context."""

    session_id: str
    game_id: str
    player_id: str
    session_seed: int

    def __post_init__(self) -> None:
        """Sessionを識別する文字列を正規化する."""
        for field_name in ("session_id", "game_id", "player_id"):
            object.__setattr__(
                self,
                field_name,
                non_blank(getattr(self, field_name), field_name),
            )


@dataclass(frozen=True)
class ObservedPlayer:
    """Agentへ公開できるプレイヤーidentityと生存状態."""

    player_id: str
    name: str
    alive: bool

    def __post_init__(self) -> None:
        """公開identityを正規化する."""
        object.__setattr__(self, "player_id", non_blank(self.player_id, "player_id"))
        object.__setattr__(self, "name", non_blank(self.name, "name"))


@dataclass(frozen=True)
class AgentObservation:
    """完全stateを含まない本人用のimmutable observation."""

    phase: str
    day: int
    me: ObservedPlayer
    players: tuple[ObservedPlayer, ...]
    known_roles: Mapping[str, str] = field(default_factory=dict)
    known_factions: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Observation内部の所有者と可視identityを検証する."""
        object.__setattr__(self, "phase", non_blank(self.phase, "phase"))
        if self.day < 1:
            raise ValueError("day must be at least 1")
        object.__setattr__(self, "players", tuple(self.players))
        player_ids = tuple(player.player_id for player in self.players)
        if len(player_ids) != len(set(player_ids)):
            raise ValueError("players must have unique player IDs")
        if self.me.player_id not in player_ids:
            raise ValueError("me must be included in players")
        if (
            next(player for player in self.players if player.player_id == self.me.player_id)
            != self.me
        ):
            raise ValueError("me must match the corresponding visible player")
        object.__setattr__(
            self,
            "known_roles",
            _identity_mapping(self.known_roles, player_ids, "known_roles"),
        )
        object.__setattr__(
            self,
            "known_factions",
            _identity_mapping(self.known_factions, player_ids, "known_factions"),
        )


@dataclass(frozen=True)
class PublicTimelineEvent:
    """Agentが根拠として参照できる一つの公開event."""

    sequence: int
    event_type: str
    day: int
    actor_id: str | None = None
    payload: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """公開eventの順序値、identity、payloadを検証する."""
        if self.sequence < 1:
            raise ValueError("sequence must be at least 1")
        if self.day < 1:
            raise ValueError("day must be at least 1")
        object.__setattr__(self, "event_type", non_blank(self.event_type, "event_type"))
        object.__setattr__(
            self,
            "actor_id",
            optional_non_blank(self.actor_id, "actor_id"),
        )
        object.__setattr__(self, "payload", _freeze_mapping(self.payload))


@dataclass(frozen=True)
class DecisionOption:
    """一つの合法actionと選択可能なtargetを表す."""

    action_type: str
    ability_id: str | None = None
    legal_target_ids: tuple[str, ...] = ()
    message_max_chars: int | None = None

    def __post_init__(self) -> None:
        """Action keyと合法targetを正規化する."""
        object.__setattr__(self, "action_type", non_blank(self.action_type, "action_type"))
        object.__setattr__(
            self,
            "ability_id",
            optional_non_blank(self.ability_id, "ability_id"),
        )
        targets = tuple(non_blank(target, "legal_target_id") for target in self.legal_target_ids)
        if len(targets) != len(set(targets)):
            raise ValueError("legal_target_ids must be unique")
        object.__setattr__(self, "legal_target_ids", targets)
        if self.message_max_chars is not None and self.message_max_chars < 1:
            raise ValueError("message_max_chars must be at least 1")

    @property
    def key(self) -> str:
        """能力IDを含む安定したaction keyを返す."""
        return f"{self.action_type}:{self.ability_id}" if self.ability_id else self.action_type


@dataclass(frozen=True)
class DecisionRequest:
    """一回の同期意思決定へ渡す秘匿性検証済み入力."""

    decision_id: str
    context: AgentContext
    observation: AgentObservation
    public_timeline: tuple[PublicTimelineEvent, ...]
    options: tuple[DecisionOption, ...]
    decision_seed: int
    deadline_at: datetime | None = None

    def __post_init__(self) -> None:
        """一回の意思決定入力の秘匿性と参照整合を検証する."""
        object.__setattr__(self, "decision_id", non_blank(self.decision_id, "decision_id"))
        if self.context.player_id != self.observation.me.player_id:
            raise ValueError("context player must match observation owner")
        object.__setattr__(self, "public_timeline", tuple(self.public_timeline))
        sequences = tuple(event.sequence for event in self.public_timeline)
        if sequences != tuple(sorted(sequences)) or len(sequences) != len(set(sequences)):
            raise ValueError("public_timeline sequences must be unique and ordered")
        object.__setattr__(self, "options", tuple(self.options))
        option_keys = tuple(option.key for option in self.options)
        if not option_keys or len(option_keys) != len(set(option_keys)):
            raise ValueError("options must be non-empty and have unique keys")
        visible_ids = {player.player_id for player in self.observation.players}
        if any(
            event.actor_id is not None and event.actor_id not in visible_ids
            for event in self.public_timeline
        ):
            raise ValueError("public timeline actors must be visible players")
        if any(
            target not in visible_ids
            for option in self.options
            for target in option.legal_target_ids
        ):
            raise ValueError("legal targets must be visible players")
        if self.deadline_at is not None and self.deadline_at.utcoffset() is None:
            raise ValueError("deadline_at must be timezone-aware")


@dataclass(frozen=True)
class DecisionResponse:
    """Agent Sessionが返す構造化された意思決定."""

    action_type: str
    ability_id: str | None = None
    target_id: str | None = None
    message: str | None = None
    focus_id: str | None = None
    evidence_id: str | None = None
    confidence: float | None = None
    beliefs: Mapping[str, float] = field(default_factory=dict)
    intent: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """構造化出力と任意分析値を正規化する."""
        object.__setattr__(self, "action_type", non_blank(self.action_type, "action_type"))
        for field_name in (
            "ability_id",
            "target_id",
            "message",
            "focus_id",
            "evidence_id",
            "intent",
        ):
            object.__setattr__(
                self,
                field_name,
                optional_non_blank(getattr(self, field_name), field_name),
            )
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        beliefs = {
            non_blank(player_id, "belief player ID"): float(value)
            for player_id, value in self.beliefs.items()
        }
        if any(not 0 <= value <= 1 for value in beliefs.values()):
            raise ValueError("belief values must be between 0 and 1")
        object.__setattr__(self, "beliefs", MappingProxyType(beliefs))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True)
class DecisionTrace:
    """chain-of-thoughtを含まない一回の意思決定診断."""

    decision_id: str
    agent_id: str
    response: DecisionResponse | None
    latency_ms: int
    fallback_used: bool = False
    error_code: str | None = None
    diagnostics: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """公開可能な診断値を正規化する."""
        object.__setattr__(self, "decision_id", non_blank(self.decision_id, "decision_id"))
        object.__setattr__(self, "agent_id", non_blank(self.agent_id, "agent_id"))
        if self.latency_ms < 0:
            raise ValueError("latency_ms must not be negative")
        object.__setattr__(
            self,
            "error_code",
            optional_non_blank(self.error_code, "error_code"),
        )
        object.__setattr__(self, "diagnostics", _freeze_mapping(self.diagnostics))


@runtime_checkable
class AgentSession(Protocol):
    """一つのgameとplayerだけに所有される同期Agent Session."""

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        """一つの検証可能な意思決定を返す."""
        ...

    def close(self) -> None:
        """Session固有resourceを冪等に解放する."""
        ...


@runtime_checkable
class AgentFactory(Protocol):
    """外部注入するAgent Sessionの生成契約."""

    @property
    def spec(self) -> AgentSpec:
        """実装と固定parameterのidentityを返す."""
        ...

    def create(self, context: AgentContext) -> AgentSession:
        """gameとplayerごとに分離した新しいSessionを返す."""
        ...


def _identity_mapping(
    values: Mapping[str, str],
    player_ids: tuple[str, ...],
    field_name: str,
) -> Mapping[str, str]:
    visible = set(player_ids)
    normalized = {
        non_blank(player_id, f"{field_name} player ID"): non_blank(value, field_name)
        for player_id, value in values.items()
    }
    if not set(normalized) <= visible:
        raise ValueError(f"{field_name} may reference only visible players")
    return MappingProxyType(normalized)


def _freeze_mapping(values: Mapping[str, object]) -> Mapping[str, object]:
    frozen: dict[str, object] = {}
    for key, value in values.items():
        if not isinstance(key, str):
            raise ValueError("mapping keys must be strings")
        frozen[non_blank(key, "mapping key")] = _freeze_value(value)
    return MappingProxyType(frozen)


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float) and isfinite(value):
        return value
    raise ValueError("mapping values must be JSON-compatible")


__all__ = [
    "AGENT_CONTRACT_VERSION",
    "AgentContext",
    "AgentFactory",
    "AgentObservation",
    "AgentSession",
    "AgentSpec",
    "DecisionOption",
    "DecisionRequest",
    "DecisionResponse",
    "DecisionTrace",
    "ObservedPlayer",
    "PublicTimelineEvent",
]
