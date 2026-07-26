"""LangChain-backed decision services for visible player observations."""

from __future__ import annotations

from collections.abc import Mapping

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.utils.json import parse_json_markdown

from werewolf_agent.adapters.llm.langchain.constants import (
    DEFAULT_REPAIRED_SPEECH,
)
from werewolf_agent.adapters.llm.langchain.decisions import (
    _bounded_speech,
    _deterministic_target_selector,
    _legal_targets_by_action,
)
from werewolf_agent.adapters.llm.langchain.models import _DecisionGraphState
from werewolf_agent.adapters.llm.messages import (
    MESSAGE_LLM_DECISION_PLAYER_MISMATCH,
    message_llm_decision_action_unavailable,
    message_llm_decision_target_unavailable,
)
from werewolf_agent.agents.models import (
    AgentActionType,
    AgentDecision,
    AgentObservation,
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
        if not isinstance(dumped, Mapping):
            return None
        if dumped.get("type") in {action.value for action in AgentActionType}:
            return dumped
        content = dumped.get("content")
        if isinstance(content, str):
            try:
                parsed = parse_json_markdown(content)
            except Exception:
                return dumped
            return parsed if isinstance(parsed, Mapping) else dumped
        return dumped
    if isinstance(raw_output, Mapping):
        parsed = raw_output.get("parsed")
        if parsed is not None:
            return _loose_mapping(parsed)
        return raw_output
    text = _output_text(raw_output)
    try:
        parsed = parse_json_markdown(text)
    except Exception:
        return None
    return parsed if isinstance(parsed, Mapping) else None


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
        if isinstance(dumped, dict) and dumped.get("type") in {
            action.value for action in AgentActionType
        }:
            parsed = dumped
        else:
            text = _output_text(raw_output)
            parsed = parse_json_markdown(text)
    elif isinstance(raw_output, Mapping):
        structured = raw_output.get("parsed")
        if structured is not None:
            return _parse_decision_output(
                structured,
                player_id=player_id,
                action_type=action_type,
                fallback_target_id=fallback_target_id,
                legal_target_ids=legal_target_ids,
                parser=parser,
            )
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
