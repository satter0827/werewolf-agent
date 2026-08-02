"""外部Agentを同期Sessionとして注入する標準ライブラリ契約を定義する."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from werewolf_agent.agents.validation import non_blank, optional_non_blank

AGENT_CONTRACT_VERSION = "0.10.0"
_CANONICAL_FACTION_IDS = frozenset({"village", "werewolf", "fox"})


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
        _require_sha256(self.fingerprint, "fingerprint")
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
        _require_integer(self.session_seed, "session_seed")


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
class AgentAbility:
    """本人が利用できる一つの能力と残り回数を表す."""

    ability_id: str
    name: str
    kind: str
    remaining_uses: int | None = None

    def __post_init__(self) -> None:
        """能力の安定IDと表示情報を検証する."""
        for field_name in ("ability_id", "name", "kind"):
            object.__setattr__(
                self,
                field_name,
                non_blank(getattr(self, field_name), field_name),
            )
        if self.remaining_uses is not None:
            _require_non_negative_integer(self.remaining_uses, "remaining_uses")


@dataclass(frozen=True)
class AgentIdentity:
    """本人だけが知る役職、陣営、目的、能力を表す."""

    role_id: str
    role_name: str
    identity_faction_id: str
    identity_faction_name: str
    victory_team_id: str
    victory_team_name: str
    objective: str
    abilities: tuple[AgentAbility, ...] = ()

    def __post_init__(self) -> None:
        """本人知識をimmutableな一意の能力集合として検証する."""
        for field_name in (
            "role_id",
            "role_name",
            "identity_faction_id",
            "identity_faction_name",
            "victory_team_id",
            "victory_team_name",
            "objective",
        ):
            object.__setattr__(
                self,
                field_name,
                non_blank(getattr(self, field_name), field_name),
            )
        abilities = tuple(self.abilities)
        ability_ids = tuple(ability.ability_id for ability in abilities)
        if len(ability_ids) != len(set(ability_ids)):
            raise ValueError("abilities must have unique ability IDs")
        object.__setattr__(self, "abilities", abilities)
        for field_name in ("identity_faction_id", "victory_team_id"):
            if getattr(self, field_name) not in _CANONICAL_FACTION_IDS:
                raise ValueError(f"{field_name} must be a canonical faction ID")


@dataclass(frozen=True)
class AgentWorld:
    """全Agentへ公開できる世界観、用語、規則provenanceを表す."""

    theme_id: str
    theme_name: str
    premise: str
    setup_checksum: str
    mechanics_checksum: str
    relevant_rules: Mapping[str, object] = field(default_factory=dict)
    action_names: Mapping[str, str] = field(default_factory=dict)
    phase_names: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """公開世界観と追跡情報をimmutableに検証する."""
        for field_name in (
            "theme_id",
            "theme_name",
            "premise",
        ):
            object.__setattr__(
                self,
                field_name,
                non_blank(getattr(self, field_name), field_name),
            )
        for field_name in ("setup_checksum", "mechanics_checksum"):
            value = non_blank(getattr(self, field_name), field_name)
            _require_sha256(value, field_name)
            object.__setattr__(self, field_name, value)
        object.__setattr__(self, "relevant_rules", _freeze_mapping(self.relevant_rules))
        object.__setattr__(
            self,
            "action_names",
            _text_mapping(self.action_names, "action_names"),
        )
        object.__setattr__(
            self,
            "phase_names",
            _text_mapping(self.phase_names, "phase_names"),
        )


@dataclass(frozen=True)
class AgentProcedure:
    """現在の意思決定が属する手続きと段階を汎用IDで表す."""

    procedure_id: str
    stage_id: str
    cycle: int
    submission_mode: str

    def __post_init__(self) -> None:
        """手続きIDと進行位置を正規化する."""
        for field_name in ("procedure_id", "stage_id", "submission_mode"):
            object.__setattr__(
                self,
                field_name,
                non_blank(getattr(self, field_name), field_name),
            )
        _require_positive_integer(self.cycle, "cycle")


@dataclass(frozen=True)
class AgentObservation:
    """完全stateを含まない本人用のimmutable observation."""

    phase: str
    day: int
    me: ObservedPlayer
    players: tuple[ObservedPlayer, ...]
    known_roles: Mapping[str, str] = field(default_factory=dict)
    known_factions: Mapping[str, str] = field(default_factory=dict)
    identity: AgentIdentity | None = None
    world: AgentWorld | None = None
    procedure: AgentProcedure | None = None

    def __post_init__(self) -> None:
        """Observation内部の所有者と可視identityを検証する."""
        object.__setattr__(self, "phase", non_blank(self.phase, "phase"))
        _require_positive_integer(self.day, "day")
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
        if self.identity is not None:
            known_role = self.known_roles.get(self.me.player_id)
            if known_role is not None and known_role != self.identity.role_id:
                raise ValueError("identity role must match the known self role")
            known_faction = self.known_factions.get(self.me.player_id)
            if known_faction is not None and known_faction != self.identity.identity_faction_id:
                raise ValueError("identity faction must match the known self faction")


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
        _require_positive_integer(self.sequence, "sequence")
        _require_positive_integer(self.day, "day")
        object.__setattr__(self, "event_type", non_blank(self.event_type, "event_type"))
        object.__setattr__(
            self,
            "actor_id",
            optional_non_blank(self.actor_id, "actor_id"),
        )
        object.__setattr__(self, "payload", _freeze_mapping(self.payload))


@dataclass(frozen=True)
class EvidenceOption:
    """意思決定で参照できる型付き公開事実を表す."""

    evidence_id: str
    kind: str
    actor_id: str
    topic_id: str
    position: str | None = None

    def __post_init__(self) -> None:
        """公開事実の識別子と意味属性を正規化する."""
        object.__setattr__(self, "evidence_id", non_blank(self.evidence_id, "evidence_id"))
        if self.kind not in {"discussion", "discussion_pass"}:
            raise ValueError("evidence kind must be discussion or discussion_pass")
        object.__setattr__(self, "actor_id", non_blank(self.actor_id, "actor_id"))
        object.__setattr__(self, "topic_id", non_blank(self.topic_id, "topic_id"))
        position = optional_non_blank(self.position, "position")
        if position not in {None, "support", "oppose", "undecided"}:
            raise ValueError("evidence position is unsupported")
        object.__setattr__(self, "position", position)


@dataclass(frozen=True)
class DecisionOption:
    """一つの合法actionと選択可能なtargetを表す."""

    action_type: str
    ability_id: str | None = None
    legal_target_ids: tuple[str, ...] = ()
    legal_topic_ids: tuple[str, ...] = ()
    evidence_options: tuple[EvidenceOption, ...] = ()
    legal_reference_ids: tuple[str, ...] = ()
    legal_positions: tuple[str, ...] = ()
    legal_relations: tuple[str, ...] = ()
    message_max_chars: int | None = None
    reason_max_chars: int | None = None

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
        topics = tuple(non_blank(topic, "legal_topic_id") for topic in self.legal_topic_ids)
        if len(topics) != len(set(topics)):
            raise ValueError("legal_topic_ids must be unique")
        object.__setattr__(self, "legal_topic_ids", topics)
        evidence = tuple(self.evidence_options)
        evidence_ids = tuple(item.evidence_id for item in evidence)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence option IDs must be unique")
        object.__setattr__(self, "evidence_options", evidence)
        references = tuple(
            non_blank(reference, "legal_reference_id") for reference in self.legal_reference_ids
        )
        if len(references) != len(set(references)):
            raise ValueError("legal_reference_ids must be unique")
        object.__setattr__(self, "legal_reference_ids", references)
        positions = tuple(non_blank(item, "legal_position") for item in self.legal_positions)
        if len(positions) != len(set(positions)) or any(
            item not in {"support", "oppose", "undecided"} for item in positions
        ):
            raise ValueError("legal_positions must contain unique supported values")
        object.__setattr__(self, "legal_positions", positions)
        relations = tuple(non_blank(item, "legal_relation") for item in self.legal_relations)
        if len(relations) != len(set(relations)) or any(
            item not in {"independent", "answer", "support", "challenge", "revise"}
            for item in relations
        ):
            raise ValueError("legal_relations must contain unique supported values")
        object.__setattr__(self, "legal_relations", relations)
        if self.message_max_chars is not None:
            _require_positive_integer(self.message_max_chars, "message_max_chars")
        if self.reason_max_chars is not None:
            _require_positive_integer(self.reason_max_chars, "reason_max_chars")

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
        _require_integer(self.decision_seed, "decision_seed")
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
        if any(
            topic not in visible_ids for option in self.options for topic in option.legal_topic_ids
        ):
            raise ValueError("legal topics must identify visible players")
        if any(
            evidence.actor_id not in visible_ids or evidence.topic_id not in visible_ids
            for option in self.options
            for evidence in option.evidence_options
        ):
            raise ValueError("evidence options may reference only visible players")
        visible_reference_ids = {
            reference_id
            for event in self.public_timeline
            if event.event_type == "speech"
            and event.actor_id is not None
            and isinstance(event.payload.get("utterance"), str)
            and str(event.payload["utterance"]).strip()
            for reference_id in (event.payload.get("speech_id"),)
            if isinstance(reference_id, str) and reference_id.strip()
        }
        if any(
            reference not in visible_reference_ids
            for option in self.options
            for reference in option.legal_reference_ids
        ):
            raise ValueError("legal references must identify visible speeches")
        if self.deadline_at is not None and self.deadline_at.utcoffset() is None:
            raise ValueError("deadline_at must be timezone-aware")


@dataclass(frozen=True)
class DecisionResponse:
    """Agent Sessionが返す構造化された意思決定."""

    action_type: str
    ability_id: str | None = None
    target_id: str | None = None
    utterance: str | None = None
    topic_id: str | None = None
    position: str | None = None
    relation: str | None = None
    evidence_id: str | None = None
    response_to_id: str | None = None
    reason: str | None = None
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
            "utterance",
            "topic_id",
            "position",
            "relation",
            "evidence_id",
            "response_to_id",
            "reason",
            "intent",
        ):
            object.__setattr__(
                self,
                field_name,
                optional_non_blank(getattr(self, field_name), field_name),
            )
        if self.confidence is not None:
            object.__setattr__(
                self,
                "confidence",
                _probability(self.confidence, "confidence"),
            )
        beliefs = {
            non_blank(player_id, "belief player ID"): _probability(value, "belief value")
            for player_id, value in self.beliefs.items()
        }
        object.__setattr__(self, "beliefs", MappingProxyType(beliefs))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True)
class DecisionTrace:
    """chain-of-thoughtを含まない一回の意思決定診断."""

    decision_id: str
    agent_spec: AgentSpec
    response: DecisionResponse | None
    latency_ms: int
    fallback_used: bool = False
    error_code: str | None = None
    diagnostics: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """公開可能な診断値を正規化する."""
        object.__setattr__(self, "decision_id", non_blank(self.decision_id, "decision_id"))
        _require_non_negative_integer(self.latency_ms, "latency_ms")
        object.__setattr__(
            self,
            "error_code",
            optional_non_blank(self.error_code, "error_code"),
        )
        if self.response is None and self.error_code is None:
            raise ValueError("trace must contain a response or error_code")
        if self.fallback_used and self.response is None:
            raise ValueError("fallback trace must contain a response")
        if self.fallback_used and self.error_code is None:
            raise ValueError("fallback trace must contain an error_code")
        if not self.fallback_used and self.response is not None and self.error_code is not None:
            raise ValueError("successful trace must not contain an error_code")
        object.__setattr__(self, "diagnostics", _freeze_mapping(self.diagnostics))


class AgentDecisionError(RuntimeError):
    """予定されたAgent失敗を安定codeと診断値で通知する."""

    def __init__(
        self,
        code: str,
        diagnostics: Mapping[str, object] | None = None,
    ) -> None:
        """検証済みcodeとimmutableな診断値を保持する."""
        self.code = non_blank(code, "code")
        self.diagnostics = _freeze_mapping(diagnostics or {})
        super().__init__(self.code)


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


def _text_mapping(values: Mapping[str, str], field_name: str) -> Mapping[str, str]:
    return MappingProxyType(
        {
            non_blank(key, f"{field_name} key"): non_blank(value, field_name)
            for key, value in values.items()
        }
    )


def _require_integer(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _require_non_negative_integer(value: object, field_name: str) -> None:
    normalized = _require_integer(value, field_name)
    if normalized < 0:
        raise ValueError(f"{field_name} must not be negative")


def _require_positive_integer(value: object, field_name: str) -> None:
    normalized = _require_integer(value, field_name)
    if normalized < 1:
        raise ValueError(f"{field_name} must be at least 1")


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _probability(value: object, field_name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric")
    normalized = float(value)
    if not isfinite(normalized) or not 0 <= normalized <= 1:
        raise ValueError(f"{field_name} must be finite and between 0 and 1")
    return normalized


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
    "AgentAbility",
    "AgentContext",
    "AgentDecisionError",
    "AgentFactory",
    "AgentIdentity",
    "AgentObservation",
    "AgentProcedure",
    "AgentSession",
    "AgentSpec",
    "AgentWorld",
    "DecisionOption",
    "DecisionRequest",
    "DecisionResponse",
    "DecisionTrace",
    "EvidenceOption",
    "ObservedPlayer",
    "PublicTimelineEvent",
]
