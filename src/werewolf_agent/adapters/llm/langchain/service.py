"""LangChain-backed decision services for visible player observations."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast

from langchain_core.language_models.fake import FakeListLLM
from langchain_core.output_parsers import PydanticOutputParser

from werewolf_agent.adapters.llm.langchain.constants import (
    DECISION_GRAPH_NODE_BUILD_PROMPT_CONTEXT,
    DECISION_GRAPH_NODE_CHOOSE_REQUIRED_ACTION,
    DECISION_GRAPH_NODE_DETERMINISTIC_FALLBACK,
    DECISION_GRAPH_NODE_INVOKE_MODEL,
    DECISION_GRAPH_NODE_NORMALIZE_OBSERVATION,
    DECISION_GRAPH_NODE_RANK_TARGETS,
    DECISION_GRAPH_NODE_REPAIR_ONCE,
    DECISION_GRAPH_NODE_ROLE_HINT,
    DECISION_GRAPH_NODE_VALIDATE_ACTION,
    DECISION_GRAPH_REVISION,
    ERROR_TYPE_GRAPH_INVOCATION,
    ERROR_TYPE_STRUCTURED_OUTPUT_UNSUPPORTED,
    FALLBACK_REASON_MODEL_ERROR,
    FALLBACK_REASON_REPAIR_FAILED,
    LLM_FALLBACK_POLICY_DETERMINISTIC_LEGAL_ACTION,
    LLM_STRUCTURED_OUTPUT_MODE_DISABLED,
    LLM_STRUCTURED_OUTPUT_MODE_REQUIRED,
    ROUTE_FAILED,
    ROUTE_FALLBACK,
    ROUTE_INVALID,
    ROUTE_VALID,
    VALIDATION_STATUS_FAILED,
    VALIDATION_STATUS_FALLBACK,
    VALIDATION_STATUS_INVALID,
    VALIDATION_STATUS_VALID,
)
from werewolf_agent.adapters.llm.langchain.decisions import (
    _fallback_decision,
    _legal_targets_by_action,
    _missing_target_reason,
    _ranked_targets_by_action,
    _selected_action,
    _speech_too_long,
    _target_for_action,
)
from werewolf_agent.adapters.llm.langchain.graph import (
    _compile_decision_graph,
    _preflight_decision,
)
from werewolf_agent.adapters.llm.langchain.models import _DecisionGraphState, _ModelDecisionPayload
from werewolf_agent.adapters.llm.langchain.parsing import (
    _is_invalid_validated_decision,
    _parse_decision_output,
    _repair_payload,
    _validated_decision,
)
from werewolf_agent.adapters.llm.langchain.prompting import (
    _elapsed_ms,
    _json_mapping,
    _prompt_hash,
    _prompt_inputs,
    _prompt_messages,
    _to_chat_prompt,
    _trace_error_payload,
    _trace_request_payload,
)
from werewolf_agent.adapters.llm.messages import (
    MESSAGE_LLM_MODEL_NOT_CONFIGURED,
    message_invalid_llm_decision,
)
from werewolf_agent.agents.definitions import FakeDecisionCatalog, PromptDefinition
from werewolf_agent.agents.models import (
    AgentActionType,
    AgentDecision,
    AgentObservation,
)
from werewolf_agent.agents.tracing import LlmInvocationTrace, LlmTraceSink
from werewolf_agent.contracts.error_catalog import (
    ERROR_CONTEXT_LLM_BASE_URL,
    ERROR_CONTEXT_LLM_ERROR_TYPE,
    ERROR_CONTEXT_LLM_MAX_TOKENS,
    ERROR_CONTEXT_LLM_MODEL,
    ERROR_CONTEXT_LLM_PROVIDER,
    ERROR_CONTEXT_LLM_TIMEOUT_SECONDS,
)


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


@dataclass(frozen=True)
class LangChainDecisionProvider:
    """Decision provider that renders a prompt and parses LangChain model output."""

    prompt: PromptDefinition
    model: Any | None = None
    fake_responses: FakeDecisionCatalog | None = None
    provider_name: str = ""
    model_name: str = ""
    base_url: str = ""
    timeout_seconds: float | None = None
    max_tokens: int | None = None
    structured_output_mode: str = "auto"
    validation_retry_count: int = 1
    graph_max_steps: int = 16
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
        object.__setattr__(self, "_graph", _compile_decision_graph(self))

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
                        "graph_revision": DECISION_GRAPH_REVISION,
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
                        "graph_revision": DECISION_GRAPH_REVISION,
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
            "role_hint": self.prompt.role_hints.get(role, ""),
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
            failed = int(state.get("repair_attempts", 0)) >= self.validation_retry_count
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
        repair_attempts = int(state.get("repair_attempts", 0)) + 1
        repaired = _repair_payload(state)
        if repaired is None:
            return {
                "validation_status": VALIDATION_STATUS_FAILED,
                "fallback_reason": FALLBACK_REASON_REPAIR_FAILED,
                "route": ROUTE_FAILED,
                "repair_attempts": repair_attempts,
                "graph_node": DECISION_GRAPH_NODE_REPAIR_ONCE,
            }
        return {
            "raw_output": repaired,
            "repair_attempts": repair_attempts,
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
                prompt_version=self.prompt.version,
                setup_checksum=(
                    observation.game_context.setup_checksum
                    if observation.game_context is not None
                    else ""
                ),
                mechanics_checksum=(
                    observation.game_context.mechanics_checksum
                    if observation.game_context is not None
                    else ""
                ),
                observation_checksum=hashlib.sha256(
                    json.dumps(
                        observation.model_dump(mode="json"),
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest(),
                request_payload=request_payload,
                raw_response=raw_response,
                parsed_decision=parsed_decision,
                error_payload=error_payload,
                latency_ms=latency_ms,
            )
        )
