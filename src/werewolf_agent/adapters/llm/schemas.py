"""Request-specific structured-output schemas for automated decisions."""

from __future__ import annotations

from collections.abc import Mapping

from werewolf_agent.adapters.llm.models import (
    AgentActionType,
    AgentAvailableAction,
    AgentObservation,
)


def build_decision_response_schema(
    observation: AgentObservation,
    context: Mapping[str, object],
) -> dict[str, object]:
    """Constrain provider output to the legal action shapes for one request."""
    branches = [
        _action_schema(action, observation=observation, context=context)
        for action in observation.available_actions
    ]
    return {
        "type": "object",
        "oneOf": branches,
    }


def _action_schema(
    action: AgentAvailableAction,
    *,
    observation: AgentObservation,
    context: Mapping[str, object],
) -> dict[str, object]:
    properties: dict[str, object] = {
        "type": {"const": action.type.value},
        "reason": {"type": "string"},
    }
    required = ["type"]

    if action.type is AgentActionType.SPEECH:
        message_schema: dict[str, object] = {"type": "string", "minLength": 1}
        speech_max_chars = _speech_max_chars(context)
        if speech_max_chars is not None:
            message_schema["maxLength"] = speech_max_chars
        properties["message"] = message_schema
        required.append("message")
        focus_ids = [player.id for player in observation.players if player.id != observation.me.id]
        if focus_ids:
            properties["focus_id"] = {"type": "string", "enum": focus_ids}
        references = observation.legal_references.get(action.key, [])
        if references:
            properties["response_to_id"] = {"type": "string", "enum": references}
            required.append("response_to_id")
    elif action.type in {AgentActionType.VOTE, AgentActionType.USE_ABILITY}:
        properties["target_id"] = {
            "type": "string",
            "enum": observation.legal_targets.get(action.key, []),
        }
        required.append("target_id")
        if action.type is AgentActionType.VOTE:
            properties["reason"] = {"type": "string", "minLength": 1}
            required.append("reason")
        else:
            properties["ability_id"] = {"const": action.ability_id}
            required.append("ability_id")

    evidence_ids = _evidence_ids(context)
    if action.type is not AgentActionType.PASS and evidence_ids:
        properties["evidence_id"] = {"type": "string", "enum": evidence_ids}

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _speech_max_chars(context: Mapping[str, object]) -> int | None:
    legal = context.get("legal")
    if not isinstance(legal, Mapping):
        return None
    constraints = legal.get("constraints")
    if not isinstance(constraints, Mapping):
        return None
    value = constraints.get("speech_max_chars")
    return value if isinstance(value, int) and value > 0 else None


def _evidence_ids(context: Mapping[str, object]) -> list[str]:
    evidence = context.get("evidence")
    if not isinstance(evidence, list):
        return []
    return [str(item["id"]) for item in evidence if isinstance(item, Mapping) and item.get("id")]


__all__ = ["build_decision_response_schema"]
