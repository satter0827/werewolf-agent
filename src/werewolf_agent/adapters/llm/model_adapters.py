"""LangChain chat-model implementations of the provider-independent model port."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from werewolf_agent.adapters.llm.fake_definitions import FakeDecisionCatalog
from werewolf_agent.adapters.llm.models import (
    AgentActionType,
    AgentAvailableAction,
    AgentDiscussionRelation,
    ModelMessage,
    ModelRequest,
    ModelResponse,
)
from werewolf_agent.adapters.llm.schemas import build_decision_response_schema
from werewolf_agent.contracts.error_catalog import (
    ERROR_CONTEXT_LLM_BASE_URL,
    ERROR_CONTEXT_LLM_ERROR_TYPE,
    ERROR_CONTEXT_LLM_MAX_TOKENS,
    ERROR_CONTEXT_LLM_MODEL,
    ERROR_CONTEXT_LLM_PROVIDER,
    ERROR_CONTEXT_LLM_TIMEOUT_SECONDS,
)


class LlmModelInvocationError(RuntimeError):
    """Raised when one configured chat model cannot be invoked."""

    def __init__(
        self,
        error_type: str,
        *,
        context: Mapping[str, object] | None = None,
    ) -> None:
        """Create a normalized provider invocation failure."""
        self.error_type = error_type
        self.context = dict(context or {})
        super().__init__(error_type)


@dataclass(frozen=True)
class LangChainChatDecisionModel:
    """Invoke one real LangChain chat model through the shared request contract."""

    model: Any
    provider_name: str
    model_name: str
    base_url: str = ""
    timeout_seconds: float | None = None
    max_tokens: int | None = None
    temperature: float | None = None

    def invoke(self, request: ModelRequest) -> ModelResponse:
        """Return one normalized chat response."""
        effective_timeout = _effective_timeout(self.timeout_seconds, request.task.timeout_seconds)
        invocation_model = self.model.bind(
            max_tokens=(
                min(request.task.output_token_limit, self.max_tokens)
                if self.max_tokens is not None
                else request.task.output_token_limit
            ),
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "agent_model_decision",
                    "strict": False,
                    "schema": request.response_schema,
                },
            },
            **({"timeout": effective_timeout} if effective_timeout is not None else {}),
        )
        try:
            raw = invocation_model.invoke(_langchain_messages(request.messages))
        except Exception as exc:
            error_type = type(exc).__name__
            raise LlmModelInvocationError(
                error_type,
                context=self._error_context(error_type, effective_timeout),
            ) from exc
        response = _model_response(raw, provider=self.provider_name, model=self.model_name)
        return response.model_copy(
            update={
                "metadata": {
                    **response.metadata,
                    "effective_timeout_seconds": effective_timeout,
                }
            }
        )

    def _error_context(
        self,
        error_type: str,
        effective_timeout: float | None,
    ) -> dict[str, object]:
        context: dict[str, object] = {
            ERROR_CONTEXT_LLM_ERROR_TYPE: error_type,
            ERROR_CONTEXT_LLM_PROVIDER: self.provider_name,
            ERROR_CONTEXT_LLM_MODEL: self.model_name,
        }
        if self.base_url:
            context[ERROR_CONTEXT_LLM_BASE_URL] = self.base_url
        if effective_timeout is not None:
            context[ERROR_CONTEXT_LLM_TIMEOUT_SECONDS] = effective_timeout
        if self.max_tokens is not None:
            context[ERROR_CONTEXT_LLM_MAX_TOKENS] = self.max_tokens
        return context


def _effective_timeout(configured: float | None, requested: float | None) -> float | None:
    """Return the shorter positive provider and simulation timeout."""
    values = [value for value in (configured, requested) if value is not None]
    return min(values) if values else None


@dataclass(frozen=True)
class FakeDecisionModel:
    """Generate deterministic legal fixtures through a real fake chat-model boundary."""

    catalog: FakeDecisionCatalog
    provider_name: str = "fake"
    model_name: str = "fake-list-chat-model"
    _visible_names: dict[str, str] = field(default_factory=dict, repr=False, compare=False)

    def invoke(self, request: ModelRequest) -> ModelResponse:
        """Return a deterministic AIMessage produced by FakeListChatModel."""
        context_text = json.dumps(
            request.task.context,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        context_checksum = hashlib.sha256(context_text.encode("utf-8")).hexdigest()
        if context_checksum != request.task.context_checksum:
            raise LlmModelInvocationError("fake_context_checksum_mismatch")
        prompt_text = json.dumps(
            [message.model_dump(mode="json") for message in request.messages],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if hashlib.sha256(prompt_text.encode("utf-8")).hexdigest() != request.prompt_checksum:
            raise LlmModelInvocationError("fake_prompt_checksum_mismatch")
        expected_schema = build_decision_response_schema(
            request.task.observation,
            request.task.context,
        )
        if request.response_schema != expected_schema:
            raise LlmModelInvocationError("fake_response_schema_mismatch")
        if context_text not in request.messages[-1].content:
            raise LlmModelInvocationError("fake_context_missing_from_prompt")

        action = _fake_action(request)
        target_id = _fake_target(request, action)
        response_to_id = _fake_reference(request, action)
        topic_id = _fake_topic(request, action, target_id, response_to_id)
        evidence_id = _fake_evidence_id(
            request,
            action,
            topic_id=topic_id,
            target_id=target_id,
            response_to_id=response_to_id,
        )
        position, relation = _fake_discussion_semantics(request, action, response_to_id)
        names = _player_names(request)
        evidence = _evidence_item(request, evidence_id)
        reference = _evidence_item(request, response_to_id)
        evidence_actor_id = _nested_id(evidence, "actor")
        reference_actor_id = _nested_id(reference, "actor")
        template_key = _fake_template_key(action, evidence_id, response_to_id)
        response = self.catalog.render(
            template_key,
            context={
                "player_name": names.get(request.task.player_id, request.task.player_id),
                "day": request.task.observation.day,
                "target_id": target_id or "",
                "target_name": names.get(target_id or "", target_id or ""),
                "topic_id": topic_id or "",
                "topic_name": names.get(topic_id or "", topic_id or ""),
                "evidence_id": evidence_id or "",
                "evidence_actor_name": names.get(evidence_actor_id, evidence_actor_id),
                "response_to_id": response_to_id or "",
                "reference_actor_name": names.get(reference_actor_id, reference_actor_id),
                "persona": (
                    request.task.observation.profile.personality
                    if request.task.observation.profile is not None
                    else ""
                ),
            },
            selector=int(request.task.context_checksum, 16),
        )
        payload = json.loads(response)
        if not isinstance(payload, dict):
            raise LlmModelInvocationError("fake_response_must_be_object")
        payload.pop("player_id", None)
        if action.ability_id is not None:
            payload["ability_id"] = action.ability_id
        previous_subject = _latest_own_speech_topic(request)
        if (
            action.type is AgentActionType.VOTE
            and previous_subject is not None
            and target_id != previous_subject
        ):
            payload["reason"] = "公開情報を見直し、直前の疑い先から判断を更新したため"
        if action.type is AgentActionType.SPEECH and topic_id is not None:
            payload["topic_id"] = topic_id
            payload["position"] = position
            payload["relation"] = relation
        if (
            action.type in {AgentActionType.SPEECH, AgentActionType.VOTE}
            and evidence_id is not None
        ):
            payload["evidence_id"] = evidence_id
        if action.type is AgentActionType.SPEECH and response_to_id is not None:
            payload["response_to_id"] = response_to_id
        response = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        raw = FakeListChatModel(responses=[response]).invoke(_langchain_messages(request.messages))
        return _model_response(raw, provider=self.provider_name, model=self.model_name)


def _langchain_messages(messages: tuple[ModelMessage, ...]) -> list[Any]:
    types = {"system": SystemMessage, "human": HumanMessage, "ai": AIMessage}
    return [types[message.role](content=message.content) for message in messages]


def _model_response(raw: object, *, provider: str, model: str) -> ModelResponse:
    content = getattr(raw, "content", raw)
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False, default=str)
    usage = _usage(getattr(raw, "usage_metadata", None))
    response_metadata = getattr(raw, "response_metadata", None)
    metadata = dict(response_metadata) if isinstance(response_metadata, Mapping) else {}
    finish_reason = str(metadata.get("finish_reason") or "")
    return ModelResponse(
        content=content,
        provider=provider,
        model=model,
        finish_reason=finish_reason,
        usage=usage,
        metadata=metadata,
    )


def _usage(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    usage: dict[str, int] = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        item = value.get(key)
        if isinstance(item, int) and item >= 0:
            usage[key] = item
    return usage


def _fake_action(request: ModelRequest) -> AgentAvailableAction:
    actions = request.task.observation.available_actions
    if not actions:
        return AgentAvailableAction(type=AgentActionType.PASS)
    priority = {
        AgentActionType.USE_ABILITY: 0,
        AgentActionType.VOTE: 1,
        AgentActionType.SPEECH: 2,
        AgentActionType.PASS: 3,
    }
    return min(actions, key=lambda item: (priority[item.type], item.key))


def _fake_target(request: ModelRequest, action: AgentAvailableAction) -> str | None:
    candidates = request.task.observation.legal_targets.get(action.key, [])
    if not candidates:
        return None
    if action.type is AgentActionType.VOTE:
        previous_subject = _latest_own_speech_topic(request)
        if previous_subject in candidates:
            if not _should_change_public_subject(request):
                return previous_subject
            alternatives = [candidate for candidate in candidates if candidate != previous_subject]
            if alternatives:
                candidates = alternatives
    digest = hashlib.sha256(
        f"{request.task.context_checksum}:{action.key}:target".encode()
    ).digest()
    return candidates[int.from_bytes(digest[:8], "big") % len(candidates)]


def _fake_topic(
    request: ModelRequest,
    action: AgentAvailableAction,
    target_id: str | None,
    response_to_id: str | None,
) -> str | None:
    if target_id is not None:
        return target_id
    candidates = request.task.observation.legal_topics.get(action.key, [])
    if not candidates:
        return None
    reference = next(
        (
            speech
            for speech in request.task.observation.speeches
            if speech.speech_id == response_to_id
        ),
        None,
    )
    if reference is not None:
        return reference.topic_id
    digest = hashlib.sha256(f"{request.task.context_checksum}:topic".encode()).digest()
    return candidates[int.from_bytes(digest[:8], "big") % len(candidates)]


def _latest_own_speech_topic(request: ModelRequest) -> str | None:
    observation = request.task.observation
    for speech in reversed(observation.speeches):
        if speech.player_id == observation.me.id:
            return speech.topic_id
    return None


def _should_change_public_subject(request: ModelRequest) -> bool:
    profile = request.task.observation.profile
    risk = profile.risk_tolerance if profile is not None else "medium"
    change_slots = {"low": 1, "medium": 2, "high": 3}.get(risk, 2)
    digest = hashlib.sha256(f"{request.task.context_checksum}:change-subject".encode()).digest()
    return digest[0] % 10 < change_slots


def _fake_evidence_id(
    request: ModelRequest,
    action: AgentAvailableAction,
    *,
    topic_id: str | None,
    target_id: str | None,
    response_to_id: str | None,
) -> str | None:
    if response_to_id is not None:
        return response_to_id
    options = request.task.observation.evidence_options.get(action.key, [])
    if not options:
        return None
    expected_id = target_id or topic_id
    for item in reversed(options):
        if expected_id in {item.actor_id, item.topic_id}:
            return item.id
    return None


def _fake_reference(
    request: ModelRequest,
    action: AgentAvailableAction,
) -> str | None:
    references = request.task.observation.legal_references.get(action.key, [])
    if not references:
        return None
    digest = hashlib.sha256(
        f"{request.task.context_checksum}:{action.key}:reference".encode()
    ).digest()
    return references[int.from_bytes(digest[:8], "big") % len(references)]


def _fake_discussion_semantics(
    request: ModelRequest,
    action: AgentAvailableAction,
    response_to_id: str | None,
) -> tuple[str | None, str | None]:
    if action.type is not AgentActionType.SPEECH:
        return None, None
    if response_to_id is None:
        digest = hashlib.sha256(f"{request.task.context_checksum}:position".encode()).digest()
        return ("support", "oppose", "undecided")[digest[0] % 3], "independent"
    reference = next(
        speech for speech in request.task.observation.speeches if speech.speech_id == response_to_id
    )
    allowed_relations = request.task.observation.legal_relations.get(action.key, [])
    if AgentDiscussionRelation.SUPPORT not in allowed_relations:
        raise ValueError("response action must authorize support")
    return reference.position.value, "support"


def _fake_template_key(
    action: AgentAvailableAction,
    evidence_id: str | None,
    response_to_id: str | None,
) -> str:
    if action.type is not AgentActionType.SPEECH:
        return action.type.value
    if response_to_id is not None:
        return "speech_response"
    return "speech_opening_evidence" if evidence_id is not None else "speech_opening_question"


def _evidence_item(request: ModelRequest, evidence_id: str | None) -> Mapping[str, object]:
    if evidence_id is None:
        return {}
    evidence = request.task.context.get("argument_ledger")
    if not isinstance(evidence, list):
        return {}
    return next(
        (
            item
            for item in evidence
            if isinstance(item, Mapping) and str(item.get("id") or "") == evidence_id
        ),
        {},
    )


def _nested_id(item: Mapping[str, object], key: str) -> str:
    nested = item.get(key)
    if not isinstance(nested, Mapping):
        return ""
    return str(nested.get("id") or "")


def _player_names(request: ModelRequest) -> dict[str, str]:
    return {player.id: player.name for player in request.task.observation.players}


__all__ = [
    "FakeDecisionModel",
    "LangChainChatDecisionModel",
    "LlmModelInvocationError",
]
