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
    branches: list[dict[str, object]] = []
    for action in observation.available_actions:
        references = observation.legal_references.get(action.key, [])
        if action.type is AgentActionType.SPEECH and references:
            branches.extend(
                _action_schema(
                    action,
                    observation=observation,
                    context=context,
                    response_reference_id=reference_id,
                )
                for reference_id in references
            )
        elif action.type is AgentActionType.SPEECH and observation.legal_evidence.get(
            action.key, []
        ):
            branches.extend(
                _action_schema(
                    action,
                    observation=observation,
                    context=context,
                    opening_mode=opening_mode,
                )
                for opening_mode in ("question", "assertion")
            )
        elif action.type is AgentActionType.VOTE and observation.legal_targets.get(action.key, []):
            branches.extend(
                _action_schema(
                    action,
                    observation=observation,
                    context=context,
                    vote_target_id=target_id,
                )
                for target_id in observation.legal_targets[action.key]
            )
        else:
            branches.append(_action_schema(action, observation=observation, context=context))
    return {
        "type": "object",
        "oneOf": branches,
    }


def _action_schema(
    action: AgentAvailableAction,
    *,
    observation: AgentObservation,
    context: Mapping[str, object],
    response_reference_id: str | None = None,
    opening_mode: str | None = None,
    vote_target_id: str | None = None,
) -> dict[str, object]:
    properties: dict[str, object] = {
        "type": {"const": action.type.value},
    }
    required = ["type"]

    if action.type is AgentActionType.SPEECH:
        message_schema: dict[str, object] = {"type": "string", "minLength": 1}
        speech_max_chars = _speech_max_chars(context)
        if speech_max_chars is not None:
            message_schema["maxLength"] = speech_max_chars
        properties["message"] = message_schema
        required.append("message")
        subject_ids = observation.legal_subjects.get(action.key, [])
        if subject_ids:
            properties["subject_id"] = {"type": "string", "enum": subject_ids}
            required.append("subject_id")
        references = observation.legal_references.get(action.key, [])
        if references:
            properties["speech_act"] = {
                "type": "string",
                "enum": ["answer", "support", "challenge", "revise"],
            }
            if response_reference_id is None:
                raise ValueError("response schema requires one reference branch")
            properties["response_to_id"] = {"const": response_reference_id}
            properties["evidence_id"] = {"const": response_reference_id}
            required.extend(("speech_act", "response_to_id", "evidence_id"))
        else:
            evidence_ids = observation.legal_evidence.get(action.key, [])
            properties["speech_act"] = (
                {"type": "string", "enum": ["support", "challenge", "revise"]}
                if opening_mode == "assertion"
                else {"const": "question"}
            )
            required.append("speech_act")
            if evidence_ids and opening_mode == "assertion":
                properties["evidence_id"] = {"type": "string", "enum": evidence_ids}
                required.append("evidence_id")
    elif action.type in {AgentActionType.VOTE, AgentActionType.USE_ABILITY}:
        properties["target_id"] = (
            {"const": vote_target_id}
            if action.type is AgentActionType.VOTE and vote_target_id is not None
            else {
                "type": "string",
                "enum": observation.legal_targets.get(action.key, []),
            }
        )
        required.append("target_id")
        if action.type is AgentActionType.VOTE:
            properties["reason"] = {
                "type": "string",
                "minLength": 1,
                "maxLength": _vote_reason_max_chars(context),
            }
            required.append("reason")
            evidence_ids = observation.legal_evidence.get(action.key, [])
            if evidence_ids:
                properties["evidence_id"] = {
                    "type": "string",
                    "enum": _target_evidence_ids(
                        context,
                        target_id=vote_target_id,
                        legal_evidence_ids=evidence_ids,
                    ),
                }
                required.append("evidence_id")
        else:
            properties["ability_id"] = {"const": action.ability_id}
            required.append("ability_id")

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


def _vote_reason_max_chars(context: Mapping[str, object]) -> int:
    legal = context.get("legal")
    if not isinstance(legal, Mapping):
        return 120
    constraints = legal.get("constraints")
    if not isinstance(constraints, Mapping):
        return 120
    value = constraints.get("vote_reason_max_chars")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 120


def _target_evidence_ids(
    context: Mapping[str, object],
    *,
    target_id: str | None,
    legal_evidence_ids: list[str],
) -> list[str]:
    public_value = context.get("public_evidence")
    public_evidence = public_value if isinstance(public_value, list) else []
    related = [
        str(item["id"])
        for item in public_evidence
        if isinstance(item, Mapping)
        and item.get("id") in legal_evidence_ids
        and target_id in {_nested_id(item.get("actor")), _nested_id(item.get("subject"))}
    ]
    return related or legal_evidence_ids


def _nested_id(value: object) -> str | None:
    return str(value.get("id")) if isinstance(value, Mapping) and value.get("id") else None


__all__ = ["build_decision_response_schema"]
