"""LangChain-backed decision services for visible player observations."""

from __future__ import annotations

import json
import time
from collections.abc import Hashable, Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Final, TypedDict, cast

from langchain_core.language_models.fake import FakeListLLM
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.utils.json import parse_json_markdown
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from werewolf_agent.agents.models import (
    AgentActionType,
    AgentDecision,
    AgentObservation,
    AgentPhase,
    AgentPlayerStatus,
    VisiblePlayer,
)
from werewolf_agent.agents.tracing import LlmInvocationTrace, LlmTraceSink
from werewolf_agent.configuration.definitions import (
    AgentStrategyDefinition,
    FakeDecisionCatalog,
    PromptDefinition,
)
from werewolf_agent.configuration.messages import (
    MESSAGE_LLM_DECISION_PLAYER_MISMATCH,
    MESSAGE_LLM_MODEL_NOT_CONFIGURED,
    MESSAGE_NO_ATTACK_TARGETS,
    MESSAGE_NO_GUARD_TARGETS,
    MESSAGE_NO_INSPECT_TARGETS,
    MESSAGE_NO_TARGET,
    MESSAGE_NO_VALID_VOTE_TARGETS,
    MESSAGE_OBSERVATION_BELONGS_TO_ANOTHER_PLAYER,
    MESSAGE_PLAYER_IS_DEAD,
    message_invalid_llm_decision,
    message_llm_decision_action_unavailable,
    message_llm_decision_target_unavailable,
    message_no_action_for_phase,
)
from werewolf_agent.contracts.error_catalog import (
    ERROR_CONTEXT_LLM_BASE_URL,
    ERROR_CONTEXT_LLM_ERROR_TYPE,
    ERROR_CONTEXT_LLM_MAX_TOKENS,
    ERROR_CONTEXT_LLM_MODEL,
    ERROR_CONTEXT_LLM_PROVIDER,
    ERROR_CONTEXT_LLM_TIMEOUT_SECONDS,
)

DETERMINISTIC_SELECTOR_BYTES: Final = 8
PROMPT_JSON_SEPARATORS: Final[tuple[str, str]] = (",", ":")
PROMPT_RECENT_SPEECH_LIMIT: Final = 3
PROMPT_RECENT_VOTE_ROUND_LIMIT: Final = 2
LLM_SPEECH_MESSAGE_MAX_CHARS: Final = 80
SECONDS_TO_MILLISECONDS: Final = 1000
DECISION_GRAPH_START: Final = "START"
DECISION_GRAPH_END: Final = "END"
DECISION_GRAPH_NODE_NORMALIZE_OBSERVATION: Final = "normalize_observation"
DECISION_GRAPH_NODE_CHOOSE_REQUIRED_ACTION: Final = "choose_required_action"
DECISION_GRAPH_NODE_ROLE_HINT: Final = "role_hint"
DECISION_GRAPH_NODE_RANK_TARGETS: Final = "rank_targets"
DECISION_GRAPH_NODE_BUILD_PROMPT_CONTEXT: Final = "build_prompt_context"
DECISION_GRAPH_NODE_INVOKE_MODEL: Final = "invoke_model"
DECISION_GRAPH_NODE_VALIDATE_ACTION: Final = "validate_action"
DECISION_GRAPH_NODE_REPAIR_ONCE: Final = "repair_once"
DECISION_GRAPH_NODE_DETERMINISTIC_FALLBACK: Final = "deterministic_fallback"
LLM_FALLBACK_POLICY_DETERMINISTIC_LEGAL_ACTION: Final = "deterministic_legal_action"
LLM_STRUCTURED_OUTPUT_MODE_DISABLED: Final = "disabled"
LLM_STRUCTURED_OUTPUT_MODE_REQUIRED: Final = "required"
VALIDATION_STATUS_VALID: Final = "valid"
VALIDATION_STATUS_INVALID: Final = "invalid"
VALIDATION_STATUS_FAILED: Final = "failed"
VALIDATION_STATUS_FALLBACK: Final = "fallback"
ROUTE_VALID: Final = "valid"
ROUTE_INVALID: Final = "invalid"
ROUTE_FAILED: Final = "failed"
ROUTE_FALLBACK: Final = "fallback"
ERROR_TYPE_GRAPH_INVOCATION: Final = "graph_invocation"
ERROR_TYPE_STRUCTURED_OUTPUT_UNSUPPORTED: Final = "structured_output_unsupported"
FALLBACK_REASON_MODEL_ERROR: Final = "model_error"
FALLBACK_REASON_REPAIR_FAILED: Final = "repair_failed"
DEFAULT_REPAIRED_SPEECH: Final = "I will watch the table and stay concise."


class LlmModelInvocationError(RuntimeError):
    """Raised when a configured real LLM model cannot be invoked."""

    def __init__(
        self,
        error_type: str,
        *,
        context: Mapping[str, object] | None = None,
    ) -> None:
        """Initialize an invocation error with safe diagnostic context."""
        self.error_type = error_type
        self.context = dict(context or {})
        super().__init__(error_type)


class _ModelDecisionPayload(BaseModel):
    """Minimal structured-output payload requested from compatible chat models."""

    type: str | None = None
    target_id: str | None = None
    message: str | None = None
    reason: str = ""


class _DecisionGraphState(TypedDict, total=False):
    player_id: str
    agent_strategy_id: str
    decision_graph_id: str
    observation: AgentObservation
    action_type: AgentActionType
    target_id: str | None
    prompt_value: Any
    prompt_messages: list[Mapping[str, object]]
    raw_output: object
    decision: AgentDecision
    validation_status: str
    validation_error: str
    fallback_reason: str
    role_hint: str
    target_rankings: dict[str, list[str]]
    invoke_error_payload: Mapping[str, object]
    graph_node: str
    route: str
    repair_attempted: bool
    started_at: float


@dataclass(frozen=True)
class LangChainDecisionProvider:
    """Decision provider that renders a prompt and parses LangChain model output."""

    prompt: PromptDefinition
    agent_strategy: AgentStrategyDefinition
    model: Any | None = None
    fake_responses: FakeDecisionCatalog | None = None
    provider_name: str = ""
    model_name: str = ""
    base_url: str = ""
    timeout_seconds: float | None = None
    max_tokens: int | None = None
    structured_output_mode: str = "auto"
    validation_retry_count: int = 1
    graph_max_steps: int = 8
    fallback_policy: str = LLM_FALLBACK_POLICY_DETERMINISTIC_LEGAL_ACTION
    trace_sink: LlmTraceSink | None = field(default=None, repr=False, compare=False)
    parser: PydanticOutputParser[AgentDecision] = field(
        default_factory=lambda: PydanticOutputParser(pydantic_object=AgentDecision)
    )
    _graph: Any = field(init=False, repr=False, compare=False)
    _fake_model: FakeListLLM | None = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Compile the configured decision graph once for this provider."""
        fake_model = None
        if self.fake_responses is not None:
            responses = [
                response.content
                for action_type in sorted(self.fake_responses.templates)
                for response in self.fake_responses.templates[action_type]
            ]
            fake_model = FakeListLLM(responses=responses)
        object.__setattr__(self, "_fake_model", fake_model)
        object.__setattr__(self, "_graph", _compile_decision_graph(self, self.agent_strategy))

    def choose_decision(self, player_id: str, observation: AgentObservation) -> AgentDecision:
        """Return one validated decision from visible player context."""
        preflight_decision = _preflight_decision(player_id, observation)
        if preflight_decision is not None:
            return preflight_decision

        try:
            state = cast(
                _DecisionGraphState,
                self._graph.invoke(
                    {
                        "player_id": player_id,
                        "observation": observation,
                        "agent_strategy_id": self.agent_strategy.id,
                        "decision_graph_id": self.agent_strategy.decision_graph_id,
                        "started_at": time.perf_counter(),
                        "validation_status": "",
                        "route": "",
                    },
                    config={"recursion_limit": self.graph_max_steps},
                ),
            )
        except Exception as exc:
            normalized_observation = observation.model_copy(
                update={"legal_targets": _legal_targets_by_action(observation)}
            )
            action_type = _selected_action(normalized_observation)
            decision = _fallback_decision(
                player_id,
                normalized_observation,
                action_type,
                reason=message_invalid_llm_decision(ERROR_TYPE_GRAPH_INVOCATION),
            )
            self._record_trace(
                player_id=player_id,
                observation=normalized_observation,
                prompt_messages=[],
                request_payload=_trace_request_payload(
                    action_type,
                    None,
                    state={
                        "agent_strategy_id": self.agent_strategy.id,
                        "decision_graph_id": self.agent_strategy.decision_graph_id,
                        "graph_node": DECISION_GRAPH_NODE_DETERMINISTIC_FALLBACK,
                        "validation_status": VALIDATION_STATUS_FALLBACK,
                        "route": ROUTE_FALLBACK,
                        "fallback_reason": type(exc).__name__,
                    },
                ),
                parsed_decision=decision.model_dump(mode="json"),
                error_payload={"error_type": type(exc).__name__},
                latency_ms=0,
            )
            return decision

        graph_observation = state.get("observation")
        if not isinstance(graph_observation, AgentObservation):
            graph_observation = observation
        graph_action_type = state.get("action_type")
        if not isinstance(graph_action_type, AgentActionType):
            graph_action_type = AgentActionType.PASS
        graph_target_id = state.get("target_id")
        if graph_target_id is not None:
            graph_target_id = str(graph_target_id)
        prompt_messages = state.get("prompt_messages", [])
        if not isinstance(prompt_messages, list):
            prompt_messages = []
        started_at = state.get("started_at")
        started_at_value = (
            started_at if isinstance(started_at, (int, float)) else time.perf_counter()
        )
        graph_decision = state.get("decision")
        if isinstance(graph_decision, AgentDecision):
            final_decision = graph_decision
        else:
            final_decision = _fallback_decision(
                player_id,
                graph_observation,
                graph_action_type,
                reason=message_invalid_llm_decision(FALLBACK_REASON_REPAIR_FAILED),
            )
        self._record_trace(
            player_id=player_id,
            observation=graph_observation,
            prompt_messages=prompt_messages,
            request_payload=_trace_request_payload(
                graph_action_type,
                graph_target_id,
                state=state,
            ),
            raw_response=_json_mapping(state["raw_output"]) if "raw_output" in state else None,
            parsed_decision=final_decision.model_dump(mode="json"),
            error_payload=_trace_error_payload(state),
            latency_ms=_elapsed_ms(float(started_at_value)),
        )
        return final_decision

    def _node_normalize_observation(self, state: _DecisionGraphState) -> _DecisionGraphState:
        observation = state["observation"].model_copy(
            update={"legal_targets": _legal_targets_by_action(state["observation"])}
        )
        return {"observation": observation, "graph_node": DECISION_GRAPH_NODE_NORMALIZE_OBSERVATION}

    def _node_choose_required_action(self, state: _DecisionGraphState) -> _DecisionGraphState:
        observation = state["observation"]
        action_type = _selected_action(observation)
        target_id = _target_for_action(observation, action_type)
        return {
            "action_type": action_type,
            "target_id": target_id,
            "graph_node": DECISION_GRAPH_NODE_CHOOSE_REQUIRED_ACTION,
        }

    def _node_role_hint(self, state: _DecisionGraphState) -> _DecisionGraphState:
        observation = state["observation"]
        role = observation.role or ""
        return {
            "role_hint": self.agent_strategy.role_hints.get(role, ""),
            "graph_node": DECISION_GRAPH_NODE_ROLE_HINT,
        }

    def _node_rank_targets(self, state: _DecisionGraphState) -> _DecisionGraphState:
        observation = state["observation"]
        action_type = state["action_type"]
        rankings = _ranked_targets_by_action(observation, action_type)
        if action_type not in AgentDecision.TARGET_TYPES:
            return {
                "target_rankings": rankings,
                "graph_node": DECISION_GRAPH_NODE_RANK_TARGETS,
            }
        target_id = rankings.get(action_type.value, [state.get("target_id") or ""])[0] or None
        next_observation = observation.model_copy(
            update={
                "legal_targets": {
                    **observation.legal_targets,
                    action_type: rankings.get(action_type.value, []),
                }
            }
        )
        return {
            "observation": next_observation,
            "target_id": target_id,
            "target_rankings": rankings,
            "graph_node": DECISION_GRAPH_NODE_RANK_TARGETS,
        }

    def _node_build_prompt_context(self, state: _DecisionGraphState) -> _DecisionGraphState:
        observation = state["observation"]
        action_type = state["action_type"]
        if action_type in AgentDecision.TARGET_TYPES and state.get("target_id") is None:
            return {
                "validation_status": VALIDATION_STATUS_FAILED,
                "route": ROUTE_FAILED,
                "fallback_reason": _missing_target_reason(action_type),
                "graph_node": DECISION_GRAPH_NODE_BUILD_PROMPT_CONTEXT,
            }
        prompt_value = _to_chat_prompt(self.prompt).invoke(
            _prompt_inputs(
                state["player_id"],
                observation,
                selected_action=action_type,
                parser=self.parser,
                role_hint=state.get("role_hint", ""),
                target_rankings=state.get("target_rankings"),
            )
        )
        return {
            "prompt_value": prompt_value,
            "prompt_messages": _prompt_messages(prompt_value),
            "graph_node": DECISION_GRAPH_NODE_BUILD_PROMPT_CONTEXT,
        }

    def _node_invoke_model(self, state: _DecisionGraphState) -> _DecisionGraphState:
        if "prompt_value" not in state:
            return {
                "validation_status": VALIDATION_STATUS_FAILED,
                "route": ROUTE_FAILED,
                "fallback_reason": state.get("fallback_reason", FALLBACK_REASON_MODEL_ERROR),
                "graph_node": DECISION_GRAPH_NODE_INVOKE_MODEL,
            }
        try:
            raw_output = self._invoke_model(
                state["prompt_value"],
                state["action_type"],
                state["player_id"],
                state.get("target_id"),
                state["observation"],
            )
        except LlmModelInvocationError as exc:
            return {
                "validation_status": VALIDATION_STATUS_FAILED,
                "route": ROUTE_FAILED,
                "fallback_reason": FALLBACK_REASON_MODEL_ERROR,
                "invoke_error_payload": dict(exc.context),
                "graph_node": DECISION_GRAPH_NODE_INVOKE_MODEL,
            }
        except Exception as exc:
            return {
                "validation_status": VALIDATION_STATUS_FAILED,
                "route": ROUTE_FAILED,
                "fallback_reason": FALLBACK_REASON_MODEL_ERROR,
                "invoke_error_payload": {"error_type": type(exc).__name__},
                "graph_node": DECISION_GRAPH_NODE_INVOKE_MODEL,
            }
        return {"raw_output": raw_output, "graph_node": DECISION_GRAPH_NODE_INVOKE_MODEL}

    def _node_validate_action(self, state: _DecisionGraphState) -> _DecisionGraphState:
        if state.get("validation_status") == VALIDATION_STATUS_FAILED and "raw_output" not in state:
            return {
                "decision": _fallback_decision(
                    state["player_id"],
                    state["observation"],
                    state["action_type"],
                    reason=str(state.get("fallback_reason", "")),
                ),
                "route": ROUTE_FAILED,
                "graph_node": DECISION_GRAPH_NODE_VALIDATE_ACTION,
            }
        try:
            decision = _parse_decision_output(
                state["raw_output"],
                player_id=state["player_id"],
                action_type=state["action_type"],
                fallback_target_id=None,
                legal_target_ids=state["observation"].legal_targets.get(
                    state["action_type"],
                    [],
                ),
                parser=self.parser,
            )
            if _speech_too_long(decision):
                raise ValueError(message_invalid_llm_decision("speech_too_long"))
            validated = _validated_decision(state["player_id"], state["observation"], decision)
            if _is_invalid_validated_decision(decision, validated):
                raise ValueError(validated.reason or "invalid_decision")
        except Exception as exc:
            failed = bool(state.get("repair_attempted")) or self.validation_retry_count <= 0
            return {
                "validation_status": VALIDATION_STATUS_FAILED
                if failed
                else VALIDATION_STATUS_INVALID,
                "validation_error": type(exc).__name__,
                "fallback_reason": message_invalid_llm_decision(type(exc).__name__),
                "route": ROUTE_FAILED if failed else ROUTE_INVALID,
                "graph_node": DECISION_GRAPH_NODE_VALIDATE_ACTION,
            }
        return {
            "decision": validated,
            "validation_status": VALIDATION_STATUS_VALID,
            "route": ROUTE_VALID,
            "graph_node": DECISION_GRAPH_NODE_VALIDATE_ACTION,
        }

    def _node_repair_once(self, state: _DecisionGraphState) -> _DecisionGraphState:
        repaired = _repair_payload(state)
        if repaired is None:
            return {
                "validation_status": VALIDATION_STATUS_FAILED,
                "fallback_reason": FALLBACK_REASON_REPAIR_FAILED,
                "route": ROUTE_FAILED,
                "repair_attempted": True,
                "graph_node": DECISION_GRAPH_NODE_REPAIR_ONCE,
            }
        return {
            "raw_output": repaired,
            "repair_attempted": True,
            "validation_status": "",
            "route": "",
            "graph_node": DECISION_GRAPH_NODE_REPAIR_ONCE,
        }

    def _node_deterministic_fallback(self, state: _DecisionGraphState) -> _DecisionGraphState:
        decision = _fallback_decision(
            state["player_id"],
            state["observation"],
            state.get("action_type", AgentActionType.PASS),
            reason=str(state.get("fallback_reason", "")),
        )
        return {
            "decision": decision,
            "validation_status": VALIDATION_STATUS_FALLBACK,
            "route": ROUTE_FALLBACK,
            "graph_node": DECISION_GRAPH_NODE_DETERMINISTIC_FALLBACK,
        }

    def _invoke_model(
        self,
        prompt_value: Any,
        action_type: AgentActionType,
        player_id: str,
        target_id: str | None,
        observation: AgentObservation,
    ) -> object:
        if self._fake_model is not None:
            return self._fake_model.invoke(prompt_value)
        if self.model is None:
            raise LlmModelInvocationError(
                MESSAGE_LLM_MODEL_NOT_CONFIGURED,
                context=self._invocation_error_context(MESSAGE_LLM_MODEL_NOT_CONFIGURED),
            )
        invocation_model = self._invocation_model()
        try:
            return invocation_model.invoke(prompt_value)
        except Exception as exc:
            error_type = type(exc).__name__
            raise LlmModelInvocationError(
                error_type,
                context=self._invocation_error_context(error_type),
            ) from exc

    def _invocation_model(self) -> Any:
        if self.structured_output_mode == LLM_STRUCTURED_OUTPUT_MODE_DISABLED:
            return self.model
        structured_output = getattr(self.model, "with_structured_output", None)
        if callable(structured_output):
            return structured_output(_ModelDecisionPayload)
        if self.structured_output_mode == LLM_STRUCTURED_OUTPUT_MODE_REQUIRED:
            raise LlmModelInvocationError(
                ERROR_TYPE_STRUCTURED_OUTPUT_UNSUPPORTED,
                context=self._invocation_error_context(ERROR_TYPE_STRUCTURED_OUTPUT_UNSUPPORTED),
            )
        return self.model

    def _invocation_error_context(self, error_type: str) -> dict[str, object]:
        context: dict[str, object] = {ERROR_CONTEXT_LLM_ERROR_TYPE: error_type}
        if self.provider_name:
            context[ERROR_CONTEXT_LLM_PROVIDER] = self.provider_name
        if self.model_name:
            context[ERROR_CONTEXT_LLM_MODEL] = self.model_name
        if self.base_url:
            context[ERROR_CONTEXT_LLM_BASE_URL] = self.base_url
        if self.timeout_seconds is not None:
            context[ERROR_CONTEXT_LLM_TIMEOUT_SECONDS] = self.timeout_seconds
        if self.max_tokens is not None:
            context[ERROR_CONTEXT_LLM_MAX_TOKENS] = self.max_tokens
        return context

    def _record_trace(
        self,
        *,
        player_id: str,
        observation: AgentObservation,
        prompt_messages: list[Mapping[str, object]],
        request_payload: Mapping[str, object],
        raw_response: Mapping[str, object] | None = None,
        parsed_decision: Mapping[str, object] | None = None,
        error_payload: Mapping[str, object] | None = None,
        latency_ms: float | None = None,
    ) -> None:
        if self.trace_sink is None:
            return
        self.trace_sink.record_invocation(
            LlmInvocationTrace(
                provider=self.provider_name,
                model=self.model_name,
                player_id=player_id,
                phase=observation.phase.value,
                day=observation.day,
                prompt_messages=prompt_messages,
                prompt_hash=_prompt_hash(prompt_messages),
                request_payload=request_payload,
                raw_response=raw_response,
                parsed_decision=parsed_decision,
                error_payload=error_payload,
                latency_ms=latency_ms,
            )
        )


def _compile_decision_graph(
    provider: LangChainDecisionProvider,
    strategy: AgentStrategyDefinition,
) -> Any:
    graph = StateGraph(_DecisionGraphState)
    registry = _node_registry(provider)
    for node_id in strategy.nodes:
        graph.add_node(node_id, registry[node_id])
    routed_sources = {route.from_node for route in strategy.routes}
    for edge in strategy.edges:
        if edge.from_node in routed_sources:
            continue
        graph.add_edge(_graph_endpoint(edge.from_node), _graph_endpoint(edge.to_node))
    for route in strategy.routes:
        path_map: dict[Hashable, str] = {}
        if route.valid is not None:
            path_map[ROUTE_VALID] = _graph_endpoint(route.valid)
        if route.invalid is not None:
            path_map[ROUTE_INVALID] = _graph_endpoint(route.invalid)
        if route.failed is not None:
            path_map[ROUTE_FAILED] = _graph_endpoint(route.failed)
        graph.add_conditional_edges(route.from_node, _route_validation, path_map=path_map)
    return graph.compile()


def _node_registry(provider: LangChainDecisionProvider) -> dict[str, Any]:
    return {
        DECISION_GRAPH_NODE_NORMALIZE_OBSERVATION: provider._node_normalize_observation,
        DECISION_GRAPH_NODE_CHOOSE_REQUIRED_ACTION: provider._node_choose_required_action,
        DECISION_GRAPH_NODE_ROLE_HINT: provider._node_role_hint,
        DECISION_GRAPH_NODE_RANK_TARGETS: provider._node_rank_targets,
        DECISION_GRAPH_NODE_BUILD_PROMPT_CONTEXT: provider._node_build_prompt_context,
        DECISION_GRAPH_NODE_INVOKE_MODEL: provider._node_invoke_model,
        DECISION_GRAPH_NODE_VALIDATE_ACTION: provider._node_validate_action,
        DECISION_GRAPH_NODE_REPAIR_ONCE: provider._node_repair_once,
        DECISION_GRAPH_NODE_DETERMINISTIC_FALLBACK: provider._node_deterministic_fallback,
    }


def _graph_endpoint(node_id: str) -> str:
    if node_id == DECISION_GRAPH_START:
        return START
    if node_id == DECISION_GRAPH_END:
        return END
    return node_id


def _route_validation(state: _DecisionGraphState) -> str:
    route = str(state.get("route") or ROUTE_FAILED)
    if route in {ROUTE_VALID, ROUTE_INVALID, ROUTE_FAILED}:
        return route
    return ROUTE_FAILED


def _preflight_decision(
    player_id: str,
    observation: AgentObservation,
) -> AgentDecision | None:
    if observation.me.id != player_id:
        return AgentDecision.pass_(
            player_id=player_id,
            reason=MESSAGE_OBSERVATION_BELONGS_TO_ANOTHER_PLAYER,
        )
    if observation.me.status is not AgentPlayerStatus.ALIVE:
        return AgentDecision.pass_(player_id=player_id, reason=MESSAGE_PLAYER_IS_DEAD)
    if not observation.available_actions:
        return AgentDecision.pass_(
            player_id=player_id,
            reason=message_no_action_for_phase(observation.phase.value),
        )
    return None


def _to_chat_prompt(prompt: PromptDefinition) -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [(message.role, message.langchain_content()) for message in prompt.messages]
    )


def _prompt_messages(prompt_value: Any) -> list[Mapping[str, object]]:
    messages: list[Any] = getattr(prompt_value, "to_messages", lambda: [])()
    records: list[Mapping[str, object]] = []
    for message in messages:
        records.append(
            {
                "type": str(getattr(message, "type", "")),
                "content": _json_compatible(getattr(message, "content", "")),
            }
        )
    return records


def _prompt_hash(prompt_messages: list[Mapping[str, object]]) -> str:
    payload = json.dumps(
        prompt_messages,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=PROMPT_JSON_SEPARATORS,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _trace_request_payload(
    action_type: AgentActionType,
    target_id: str | None,
    *,
    state: Mapping[str, object] | None = None,
) -> Mapping[str, object]:
    state = state or {}
    payload: dict[str, object] = {
        "agent_strategy_id": str(state.get("agent_strategy_id") or ""),
        "decision_graph_id": str(state.get("decision_graph_id") or ""),
        "graph_node": str(state.get("graph_node") or ""),
        "route": str(state.get("route") or ""),
        "validation_status": str(state.get("validation_status") or ""),
        "fallback_reason": str(state.get("fallback_reason") or ""),
        "selected_action": action_type.value,
    }
    if target_id is not None:
        payload["target_id"] = target_id
    target_rankings = state.get("target_rankings")
    if isinstance(target_rankings, Mapping):
        payload["target_rankings"] = _json_compatible(target_rankings)
    return payload


def _trace_error_payload(state: Mapping[str, object]) -> Mapping[str, object] | None:
    payload: dict[str, object] = {}
    validation_error = state.get("validation_error")
    if validation_error:
        payload["validation_error"] = str(validation_error)
    invoke_error_payload = state.get("invoke_error_payload")
    if isinstance(invoke_error_payload, Mapping):
        payload.update(
            {str(key): _json_compatible(value) for key, value in invoke_error_payload.items()}
        )
    return payload or None


def _json_mapping(value: object) -> Mapping[str, object]:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
    if isinstance(value, Mapping):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    return {"value": _json_compatible(value)}


def _json_compatible(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_compatible(item) for item in value]
    return str(value)


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * SECONDS_TO_MILLISECONDS, 3)


def _selected_action(observation: AgentObservation) -> AgentActionType:
    if observation.phase is AgentPhase.DAY_DISCUSSION:
        return _first_available(observation, AgentActionType.SPEECH)
    if observation.phase is AgentPhase.VOTING:
        return _first_available(observation, AgentActionType.VOTE)
    if observation.phase is AgentPhase.NIGHT:
        for action_type in (
            AgentActionType.WEREWOLF_ATTACK,
            AgentActionType.SEER_INSPECT,
            AgentActionType.KNIGHT_GUARD,
        ):
            if action_type in observation.available_actions:
                return action_type
    return AgentActionType.PASS


def _first_available(
    observation: AgentObservation,
    action_type: AgentActionType,
) -> AgentActionType:
    return action_type if action_type in observation.available_actions else AgentActionType.PASS


def _target_for_action(
    observation: AgentObservation,
    action_type: AgentActionType,
) -> str | None:
    candidates = _legal_targets_by_action(observation).get(action_type, [])
    if not candidates:
        return None
    selector = _deterministic_target_selector(observation.me.id, observation, action_type)
    return candidates[selector % len(candidates)]


def _ranked_targets_by_action(
    observation: AgentObservation,
    action_type: AgentActionType,
) -> dict[str, list[str]]:
    candidates = list(observation.legal_targets.get(action_type, []))
    if action_type not in AgentDecision.TARGET_TYPES or not candidates:
        return {}
    return {
        action_type.value: sorted(
            candidates,
            key=lambda player_id: (
                -_target_signal(observation, player_id),
                _stable_target_rank(observation, action_type, player_id),
            ),
        )
    }


def _target_signal(observation: AgentObservation, player_id: str) -> int:
    if not observation.vote_rounds:
        return 0
    return int(observation.vote_rounds[-1].counts.get(player_id, 0))


def _stable_target_rank(
    observation: AgentObservation,
    action_type: AgentActionType,
    player_id: str,
) -> int:
    digest = sha256(
        f"{observation.me.id}:{action_type.value}:{observation.day}:{player_id}:rank".encode()
    ).digest()
    return int.from_bytes(digest[:DETERMINISTIC_SELECTOR_BYTES], "big")


def _legal_targets_by_action(
    observation: AgentObservation,
) -> dict[AgentActionType, list[str]]:
    """Return legal target ids for available target-taking actions."""
    targets: dict[AgentActionType, list[str]] = {}
    for action_type in observation.available_actions:
        if action_type not in AgentDecision.TARGET_TYPES:
            continue
        targets[action_type] = list(observation.legal_targets.get(action_type, []))
    return targets


def _fallback_decision(
    player_id: str,
    observation: AgentObservation,
    action_type: AgentActionType,
    *,
    reason: str,
) -> AgentDecision:
    if action_type is AgentActionType.SPEECH and action_type in observation.available_actions:
        return AgentDecision.speech(player_id, _fallback_speech(observation))
    if action_type in AgentDecision.TARGET_TYPES and action_type in observation.available_actions:
        target_id = _target_for_action(observation, action_type)
        if target_id is None:
            return AgentDecision.pass_(
                player_id=player_id,
                reason=_missing_target_reason(action_type),
            )
        return _target_decision(player_id, action_type, target_id, reason=reason)
    return AgentDecision.pass_(player_id=player_id, reason=reason)


def _fallback_speech(observation: AgentObservation) -> str:
    focus = _focus_player(observation)
    if focus is None:
        return DEFAULT_REPAIRED_SPEECH
    return _bounded_speech(f"I want to compare {focus.name}'s claims with the votes.")


def _target_decision(
    player_id: str,
    action_type: AgentActionType,
    target_id: str,
    *,
    reason: str,
) -> AgentDecision:
    if action_type is AgentActionType.VOTE:
        return AgentDecision.vote(player_id, target_id, reason=reason)
    if action_type is AgentActionType.WEREWOLF_ATTACK:
        return AgentDecision.attack(player_id, target_id, reason=reason)
    if action_type is AgentActionType.SEER_INSPECT:
        return AgentDecision.inspect(player_id, target_id, reason=reason)
    if action_type is AgentActionType.KNIGHT_GUARD:
        return AgentDecision.guard(player_id, target_id, reason=reason)
    return AgentDecision.pass_(player_id=player_id, reason=reason)


def _missing_target_reason(action_type: AgentActionType) -> str:
    if action_type is AgentActionType.VOTE:
        return MESSAGE_NO_VALID_VOTE_TARGETS
    if action_type is AgentActionType.WEREWOLF_ATTACK:
        return MESSAGE_NO_ATTACK_TARGETS
    if action_type is AgentActionType.SEER_INSPECT:
        return MESSAGE_NO_INSPECT_TARGETS
    if action_type is AgentActionType.KNIGHT_GUARD:
        return MESSAGE_NO_GUARD_TARGETS
    return MESSAGE_NO_TARGET


def _deterministic_target_selector(
    player_id: str,
    observation: AgentObservation,
    action_type: AgentActionType,
) -> int:
    digest = sha256(f"{player_id}:{action_type.value}:{observation.day}:target".encode()).digest()
    return int.from_bytes(digest[:DETERMINISTIC_SELECTOR_BYTES], "big")


def _persona_text(profile: object | None) -> str:
    if profile is None:
        return ""
    personality = getattr(profile, "personality", "")
    speaking_style = getattr(profile, "speaking_style", "")
    reasoning_style = getattr(profile, "reasoning_style", "")
    risk_tolerance = getattr(profile, "risk_tolerance", "")
    return " / ".join(
        item
        for item in [personality, speaking_style, reasoning_style, f"risk={risk_tolerance}"]
        if item
    )


def _character_profile_text(profile: object | None) -> str:
    if profile is None:
        return ""
    name = getattr(profile, "name", "")
    age = getattr(profile, "age", "")
    gender = getattr(profile, "gender", "")
    personality = getattr(profile, "personality", "")
    speaking_style = getattr(profile, "speaking_style", "")
    reasoning_style = getattr(profile, "reasoning_style", "")
    risk_tolerance = getattr(profile, "risk_tolerance", "")
    return " / ".join(
        str(item)
        for item in [
            f"name={name}" if name else "",
            f"age={age}" if age else "",
            f"gender={gender}" if gender else "",
            f"personality={personality}" if personality else "",
            f"speaking_style={speaking_style}" if speaking_style else "",
            f"reasoning_style={reasoning_style}" if reasoning_style else "",
            f"risk={risk_tolerance}" if risk_tolerance else "",
        ]
        if item
    )


def _focus_player(observation: AgentObservation) -> VisiblePlayer | None:
    candidates = [
        player
        for player in observation.players
        if player.status is AgentPlayerStatus.ALIVE and player.id != observation.me.id
    ]
    if not candidates:
        return None
    selector = _deterministic_target_selector(
        observation.me.id,
        observation,
        AgentActionType.SPEECH,
    )
    return candidates[selector % len(candidates)]


def _prompt_inputs(
    player_id: str,
    observation: AgentObservation,
    *,
    selected_action: AgentActionType,
    parser: PydanticOutputParser[AgentDecision],
    role_hint: str = "",
    target_rankings: Mapping[str, list[str]] | None = None,
) -> dict[str, str]:
    _ = parser
    return {
        "player_id": player_id,
        "phase": observation.phase.value,
        "day": str(observation.day),
        "role": observation.role if observation.role is not None else "",
        "scenario_name": observation.scenario.name if observation.scenario is not None else "",
        "scenario_premise": (
            observation.scenario.premise if observation.scenario is not None else ""
        ),
        "character_profile": _character_profile_text(observation.profile),
        "available_actions": json.dumps(
            [action.value for action in observation.available_actions],
            ensure_ascii=False,
        ),
        "selected_action": selected_action.value,
        "legal_targets_json": json.dumps(
            {
                action_type.value: player_ids
                for action_type, player_ids in _legal_targets_by_action(observation).items()
            },
            ensure_ascii=False,
            separators=PROMPT_JSON_SEPARATORS,
        ),
        "observation_json": json.dumps(
            _compact_observation(
                observation,
                role_hint=role_hint,
                target_rankings=target_rankings,
            ),
            ensure_ascii=False,
            separators=PROMPT_JSON_SEPARATORS,
        ),
        "format_instructions": _decision_format_instructions(),
    }


def _compact_observation(
    observation: AgentObservation,
    *,
    role_hint: str = "",
    target_rankings: Mapping[str, list[str]] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "me": observation.me.model_dump(mode="json"),
        "players": [player.model_dump(mode="json") for player in observation.players],
        "known_roles": dict(observation.known_roles),
        "speeches": [
            speech.model_dump(mode="json")
            for speech in observation.speeches[-PROMPT_RECENT_SPEECH_LIMIT:]
        ],
        "vote_rounds": [
            vote_round.model_dump(mode="json")
            for vote_round in observation.vote_rounds[-PROMPT_RECENT_VOTE_ROUND_LIMIT:]
        ],
    }
    if role_hint:
        payload["strategy_hint"] = role_hint
    if target_rankings:
        payload["target_rankings"] = dict(target_rankings)
    return payload


def _decision_format_instructions() -> str:
    return (
        'Return JSON with keys "type", optional "target_id", optional "message", '
        'and optional "reason". Do not include "player_id"; the server sets it. '
        'Use the selected_action value as "type". Include "message" only for speech. '
        "Do not wrap the JSON in markdown fences. "
        f"Speech message must be {LLM_SPEECH_MESSAGE_MAX_CHARS} characters or less."
    )


def _repair_payload(state: _DecisionGraphState) -> Mapping[str, object] | None:
    action_type = state["action_type"]
    raw_output = state.get("raw_output")
    if raw_output is not None and _loose_mapping(raw_output) is None:
        return None
    reason = _reason_from_raw_output(raw_output) or str(state.get("fallback_reason") or "")
    if action_type is AgentActionType.SPEECH:
        message = _message_from_raw_output(raw_output) or DEFAULT_REPAIRED_SPEECH
        return {
            "type": action_type.value,
            "message": _bounded_speech(message),
            "reason": reason,
        }
    if action_type in AgentDecision.TARGET_TYPES:
        legal_targets = state["observation"].legal_targets.get(action_type, [])
        if not legal_targets:
            return None
        target_id = state.get("target_id")
        if target_id not in legal_targets:
            target_id = legal_targets[
                _deterministic_target_selector(
                    state["player_id"],
                    state["observation"],
                    action_type,
                )
                % len(legal_targets)
            ]
        return {
            "type": action_type.value,
            "target_id": target_id,
            "reason": reason,
        }
    if action_type is AgentActionType.PASS:
        return {"type": action_type.value, "reason": reason}
    return None


def _message_from_raw_output(raw_output: object) -> str:
    mapping = _loose_mapping(raw_output)
    if mapping is None:
        return ""
    return str(mapping.get("message") or "").strip()


def _reason_from_raw_output(raw_output: object) -> str:
    mapping = _loose_mapping(raw_output)
    if mapping is None:
        return ""
    return str(mapping.get("reason") or "").strip()


def _loose_mapping(raw_output: object) -> Mapping[str, object] | None:
    if hasattr(raw_output, "model_dump"):
        dumped = raw_output.model_dump(mode="json")
        return dumped if isinstance(dumped, Mapping) else None
    if isinstance(raw_output, Mapping):
        return raw_output
    text = _output_text(raw_output)
    try:
        parsed = parse_json_markdown(text)
    except Exception:
        return None
    return parsed if isinstance(parsed, Mapping) else None


def _bounded_speech(message: str) -> str:
    text = " ".join(message.strip().split())
    if len(text) <= LLM_SPEECH_MESSAGE_MAX_CHARS:
        return text
    return text[:LLM_SPEECH_MESSAGE_MAX_CHARS].rstrip()


def _speech_too_long(decision: AgentDecision) -> bool:
    return (
        decision.type is AgentActionType.SPEECH
        and decision.message is not None
        and len(decision.message) > LLM_SPEECH_MESSAGE_MAX_CHARS
    )


def _is_invalid_validated_decision(
    decision: AgentDecision,
    validated: AgentDecision,
) -> bool:
    return decision.type is not AgentActionType.PASS and validated.type is AgentActionType.PASS


def _output_text(raw_output: object) -> str:
    if isinstance(raw_output, str):
        return raw_output
    content = getattr(raw_output, "content", None)
    if isinstance(content, str):
        return content
    return str(raw_output)


def _parse_decision_output(
    raw_output: object,
    *,
    player_id: str,
    action_type: AgentActionType,
    fallback_target_id: str | None,
    legal_target_ids: list[str],
    parser: PydanticOutputParser[AgentDecision],
) -> AgentDecision:
    if hasattr(raw_output, "model_dump"):
        dumped = raw_output.model_dump(mode="json")
        parsed = dumped if isinstance(dumped, dict) else {}
    elif isinstance(raw_output, Mapping):
        parsed = {str(key): value for key, value in raw_output.items()}
    else:
        text = _output_text(raw_output)
        try:
            parsed = parse_json_markdown(text)
        except Exception:
            parsed_decision = parser.parse(text)
            parsed = parsed_decision.model_dump(mode="json")
    return AgentDecision.model_validate(
        _normalized_decision_payload(
            parsed,
            player_id=player_id,
            action_type=action_type,
            fallback_target_id=fallback_target_id,
            legal_target_ids=legal_target_ids,
        )
    )


def _normalized_decision_payload(
    parsed: object,
    *,
    player_id: str,
    action_type: AgentActionType,
    fallback_target_id: str | None,
    legal_target_ids: list[str],
) -> dict[str, object]:
    if not isinstance(parsed, dict):
        raise TypeError(type(parsed).__name__)
    payload = dict(parsed)
    payload["type"] = action_type.value
    payload["player_id"] = player_id
    if action_type is AgentActionType.SPEECH:
        payload.pop("target_id", None)
        return payload
    if action_type in AgentDecision.TARGET_TYPES:
        llm_target_id = str(payload.get("target_id") or "").strip()
        payload["target_id"] = (
            llm_target_id if llm_target_id in legal_target_ids else fallback_target_id
        )
        payload.pop("message", None)
        return payload
    if action_type is AgentActionType.PASS:
        payload.pop("target_id", None)
        payload.pop("message", None)
        return payload
    return payload


def _validated_decision(
    player_id: str,
    observation: AgentObservation,
    decision: AgentDecision,
) -> AgentDecision:
    if decision.player_id != player_id:
        return AgentDecision.pass_(player_id=player_id, reason=MESSAGE_LLM_DECISION_PLAYER_MISMATCH)
    if decision.type is AgentActionType.PASS:
        return decision
    if decision.type not in observation.available_actions:
        return AgentDecision.pass_(
            player_id=player_id,
            reason=message_llm_decision_action_unavailable(decision.type.value),
        )
    if (
        decision.type in AgentDecision.TARGET_TYPES
        and decision.target_id not in _legal_targets_by_action(observation).get(decision.type, [])
    ):
        return AgentDecision.pass_(
            player_id=player_id,
            reason=message_llm_decision_target_unavailable(decision.type.value),
        )
    return decision


__all__ = [
    "LangChainDecisionProvider",
]
