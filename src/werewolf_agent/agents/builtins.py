"""外部serviceなしで使用できる標準Agent Factoryを提供する."""

from __future__ import annotations

import json
import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256

from werewolf_agent.agents.contracts import (
    AgentContext,
    AgentDecisionError,
    AgentSession,
    AgentSpec,
    DecisionOption,
    DecisionRequest,
    DecisionResponse,
)
from werewolf_agent.agents.validation import non_blank

_BUILTIN_IMPLEMENTATION_VERSION = "1.2.0"


@dataclass(frozen=True)
class RandomLegalAgentFactory:
    """decision seedから合法手を一つ選ぶ再現可能なAgent Factory."""

    speech: str = "状況を確認します。"

    def __post_init__(self) -> None:
        """発言設定をFactory構築時に検証する."""
        object.__setattr__(self, "speech", non_blank(self.speech, "speech"))

    @property
    def spec(self) -> AgentSpec:
        """設定を含む組み込み実装identityを返す."""
        return _spec("random-legal", {"speech": self.speech})

    def create(self, context: AgentContext) -> AgentSession:
        """状態を共有しないSessionを生成する."""
        return _RandomLegalSession(context, self.speech)


@dataclass(frozen=True)
class HeuristicAgentFactory:
    """能力、投票、発言、passの順で最初の合法手を選ぶAgent Factory."""

    speech: str = "公開情報を基準に判断します。"

    def __post_init__(self) -> None:
        """発言設定をFactory構築時に検証する."""
        object.__setattr__(self, "speech", non_blank(self.speech, "speech"))

    @property
    def spec(self) -> AgentSpec:
        """設定を含む組み込み実装identityを返す."""
        return _spec("heuristic", {"speech": self.speech})

    def create(self, context: AgentContext) -> AgentSession:
        """状態を共有しないSessionを生成する."""
        return _HeuristicSession(context, self.speech)


@dataclass(frozen=True)
class ScriptedAgentFactory:
    """テストと再現実験で順番に応答を返すFake Agent Factory."""

    responses: tuple[DecisionResponse, ...]

    def __post_init__(self) -> None:
        """空のscriptを拒否して応答列を固定する."""
        object.__setattr__(self, "responses", tuple(self.responses))
        if not self.responses:
            raise ValueError("responses must not be empty")

    @property
    def spec(self) -> AgentSpec:
        """応答scriptを含む組み込み実装identityを返す."""
        return _spec(
            "scripted",
            {"responses": [_response_payload(response) for response in self.responses]},
        )

    def create(self, context: AgentContext) -> AgentSession:
        """indexを共有しないSessionを生成する."""
        return _ScriptedSession(context, self.responses)


@dataclass(frozen=True)
class FaultAgentFactory:
    """timeoutと例外処理のcontractテスト用に決定的に失敗するFactory."""

    error_code: str = "agent_fault"

    def __post_init__(self) -> None:
        """故障識別子をFactory構築時に検証する."""
        object.__setattr__(self, "error_code", non_blank(self.error_code, "error_code"))

    @property
    def spec(self) -> AgentSpec:
        """Error codeを含む組み込み実装identityを返す."""
        return _spec("fault", {"error_code": self.error_code})

    def create(self, context: AgentContext) -> AgentSession:
        """状態を共有しない故障Sessionを生成する."""
        return _FaultSession(context, self.error_code)


@dataclass
class _Session:
    context: AgentContext
    closed: bool = field(default=False, init=False)

    def close(self) -> None:
        """Sessionを冪等にcloseする."""
        self.closed = True

    def _require_request(self, request: DecisionRequest) -> None:
        if self.closed:
            raise RuntimeError("agent session is closed")
        if request.context != self.context:
            raise ValueError("request context does not belong to this session")


class _RandomLegalSession(_Session):
    def __init__(self, context: AgentContext, speech: str) -> None:
        super().__init__(context)
        self._speech = speech

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        """seedだけから一つの合法手とtargetを選ぶ."""
        self._require_request(request)
        generator = random.Random(request.decision_seed)
        option = request.options[generator.randrange(len(request.options))]
        target = (
            option.legal_target_ids[generator.randrange(len(option.legal_target_ids))]
            if option.legal_target_ids
            else None
        )
        return _response(request, option, target=target, speech=self._speech)


class _HeuristicSession(_Session):
    def __init__(self, context: AgentContext, speech: str) -> None:
        super().__init__(context)
        self._speech = speech

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        """安定したaction優先順位と最初のtargetで応答する."""
        self._require_request(request)
        priority = {"use_ability": 0, "vote": 1, "speech": 2, "pass": 3}
        option = min(
            request.options,
            key=lambda item: (priority.get(item.action_type, 4), item.key),
        )
        target = option.legal_target_ids[0] if option.legal_target_ids else None
        return _response(request, option, target=target, speech=self._speech)


class _ScriptedSession(_Session):
    def __init__(self, context: AgentContext, responses: tuple[DecisionResponse, ...]) -> None:
        super().__init__(context)
        self._responses = responses
        self._index = 0

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        """Session固有indexの次の応答を返す."""
        self._require_request(request)
        if self._index >= len(self._responses):
            raise RuntimeError("scripted agent responses are exhausted")
        response = self._responses[self._index]
        self._index += 1
        return response


class _FaultSession(_Session):
    def __init__(self, context: AgentContext, error_code: str) -> None:
        super().__init__(context)
        self._error_code = error_code

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        """設定済みerror codeで必ず失敗する."""
        self._require_request(request)
        raise AgentDecisionError(self._error_code)


def _response(
    request: DecisionRequest,
    option: DecisionOption,
    *,
    target: str | None,
    speech: str,
) -> DecisionResponse:
    utterance = None
    topic_id = None
    position = None
    relation = None
    if option.action_type == "speech":
        utterance = f"反対です。{speech}" if option.legal_reference_ids else speech
        topic_id = option.legal_topic_ids[0]
        position = "support"
        relation = "independent"
        if option.legal_reference_ids:
            referenced = next(
                item
                for item in option.evidence_options
                if item.evidence_id == option.legal_reference_ids[0]
            )
            topic_id = referenced.topic_id
            relation = "answer" if referenced.position == "undecided" else "challenge"
            position = "oppose" if referenced.position == "support" else "support"
        if option.message_max_chars:
            utterance = utterance[: option.message_max_chars]
    evidence_id = None
    if option.action_type == "speech" and option.legal_reference_ids:
        evidence_id = option.legal_reference_ids[0]
    elif option.action_type == "vote" and option.evidence_options:
        evidence_id = next(
            (
                item.evidence_id
                for item in reversed(option.evidence_options)
                if target in {item.actor_id, item.topic_id}
            ),
            option.evidence_options[0].evidence_id,
        )
    reason = "この対象が最も疑わしいため" if option.action_type == "vote" else None
    if reason is not None and option.reason_max_chars is not None:
        reason = reason[: option.reason_max_chars]
    return DecisionResponse(
        action_type=option.action_type,
        ability_id=option.ability_id,
        target_id=target,
        utterance=utterance,
        topic_id=topic_id,
        position=position,
        relation=relation,
        evidence_id=evidence_id,
        response_to_id=(option.legal_reference_ids[0] if option.legal_reference_ids else None),
        reason=reason,
    )


def _spec(agent_id: str, parameters: Mapping[str, object]) -> AgentSpec:
    canonical = _json_value(parameters)
    if not isinstance(canonical, dict):
        raise ValueError("agent parameters must be an object")
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    fingerprint = sha256(
        f"werewolf-agent:{agent_id}:{_BUILTIN_IMPLEMENTATION_VERSION}:{payload}".encode()
    ).hexdigest()
    return AgentSpec(agent_id, _BUILTIN_IMPLEMENTATION_VERSION, fingerprint, canonical)


def _response_payload(response: DecisionResponse) -> dict[str, object]:
    return {
        "action_type": response.action_type,
        "ability_id": response.ability_id,
        "target_id": response.target_id,
        "utterance": response.utterance,
        "topic_id": response.topic_id,
        "position": response.position,
        "relation": response.relation,
        "evidence_id": response.evidence_id,
        "response_to_id": response.response_to_id,
        "reason": response.reason,
        "confidence": response.confidence,
        "beliefs": _json_value(response.beliefs),
        "intent": response.intent,
        "metadata": _json_value(response.metadata),
    }


def _json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


__all__ = [
    "FaultAgentFactory",
    "HeuristicAgentFactory",
    "RandomLegalAgentFactory",
    "ScriptedAgentFactory",
]
