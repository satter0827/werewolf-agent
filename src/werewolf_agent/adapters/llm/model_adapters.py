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
    max_retries: int | None = None

    def invoke(self, request: ModelRequest) -> ModelResponse:
        """Return one normalized chat response."""
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
        )
        try:
            raw = invocation_model.invoke(_langchain_messages(request.messages))
        except Exception as exc:
            error_type = type(exc).__name__
            raise LlmModelInvocationError(
                error_type,
                context=self._error_context(error_type),
            ) from exc
        return _model_response(raw, provider=self.provider_name, model=self.model_name)

    def _error_context(self, error_type: str) -> dict[str, object]:
        context: dict[str, object] = {
            ERROR_CONTEXT_LLM_ERROR_TYPE: error_type,
            ERROR_CONTEXT_LLM_PROVIDER: self.provider_name,
            ERROR_CONTEXT_LLM_MODEL: self.model_name,
        }
        if self.base_url:
            context[ERROR_CONTEXT_LLM_BASE_URL] = self.base_url
        if self.timeout_seconds is not None:
            context[ERROR_CONTEXT_LLM_TIMEOUT_SECONDS] = self.timeout_seconds
        if self.max_tokens is not None:
            context[ERROR_CONTEXT_LLM_MAX_TOKENS] = self.max_tokens
        return context


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
        focus_id = _fake_focus(request, target_id)
        evidence_id = _fake_evidence_id(request)
        response_to_id = _fake_reference(request, action)
        names = _player_names(request)
        response = self.catalog.render(
            action.type.value,
            context={
                "player_name": names.get(request.task.player_id, request.task.player_id),
                "day": request.task.observation.day,
                "target_id": target_id or "",
                "target_name": names.get(target_id or "", target_id or ""),
                "focus_id": focus_id or "",
                "focus_name": names.get(focus_id or "", focus_id or ""),
                "evidence_id": evidence_id or "",
                "response_to_id": response_to_id or "",
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
        previous_focus = _latest_own_speech_focus(request)
        if (
            action.type is AgentActionType.VOTE
            and previous_focus is not None
            and target_id != previous_focus
        ):
            payload["reason"] = "公開情報を見直し、直前の疑い先から判断を更新したため"
        if action.type is AgentActionType.SPEECH and focus_id is not None:
            payload["focus_id"] = focus_id
        if action.type is not AgentActionType.PASS and evidence_id is not None:
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
    digest = hashlib.sha256(f"{request.task.context_checksum}:action".encode()).digest()
    return actions[int.from_bytes(digest[:8], "big") % len(actions)]


def _fake_target(request: ModelRequest, action: AgentAvailableAction) -> str | None:
    candidates = request.task.observation.legal_targets.get(action.key, [])
    if not candidates:
        return None
    if action.type is AgentActionType.VOTE:
        previous_focus = _latest_own_speech_focus(request)
        if previous_focus in candidates:
            if not _should_change_public_focus(request):
                return previous_focus
            alternatives = [candidate for candidate in candidates if candidate != previous_focus]
            if alternatives:
                candidates = alternatives
    digest = hashlib.sha256(
        f"{request.task.context_checksum}:{action.key}:target".encode()
    ).digest()
    return candidates[int.from_bytes(digest[:8], "big") % len(candidates)]


def _fake_focus(request: ModelRequest, target_id: str | None) -> str | None:
    if target_id is not None:
        return target_id
    candidates = [
        player.id
        for player in request.task.observation.players
        if player.id != request.task.player_id and player.status.value == "alive"
    ]
    if not candidates:
        return None
    digest = hashlib.sha256(f"{request.task.context_checksum}:focus".encode()).digest()
    return candidates[int.from_bytes(digest[:8], "big") % len(candidates)]


def _latest_own_speech_focus(request: ModelRequest) -> str | None:
    observation = request.task.observation
    for speech in reversed(observation.speeches):
        if speech.player_id == observation.me.id and speech.focus_id is not None:
            return speech.focus_id
    return None


def _should_change_public_focus(request: ModelRequest) -> bool:
    profile = request.task.observation.profile
    risk = profile.risk_tolerance if profile is not None else "medium"
    change_slots = {"low": 1, "medium": 2, "high": 3}.get(risk, 2)
    digest = hashlib.sha256(f"{request.task.context_checksum}:change-focus".encode()).digest()
    return digest[0] % 10 < change_slots


def _fake_evidence_id(request: ModelRequest) -> str | None:
    evidence = request.task.context.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return None
    first = evidence[0]
    if not isinstance(first, Mapping):
        return None
    value = first.get("id")
    return str(value) if value else None


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


def _player_names(request: ModelRequest) -> dict[str, str]:
    return {player.id: player.name for player in request.task.observation.players}


__all__ = [
    "FakeDecisionModel",
    "LangChainChatDecisionModel",
    "LlmModelInvocationError",
]
