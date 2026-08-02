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
            for reference_id in references:
                for relation, position in _response_variants(
                    observation,
                    action.key,
                    reference_id,
                ):
                    branches.append(
                        _action_schema(
                            action,
                            observation=observation,
                            context=context,
                            response_reference_id=reference_id,
                            response_relation=relation,
                            response_position=position,
                        )
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
    response_relation: str | None = None,
    response_position: str | None = None,
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
        properties["utterance"] = message_schema
        required.append("utterance")
        topic_ids = observation.legal_topics.get(action.key, [])
        references = observation.legal_references.get(action.key, [])
        if references:
            referenced = next(
                speech
                for speech in observation.speeches
                if speech.speech_id == response_reference_id
            )
            if (
                response_reference_id is None
                or response_relation is None
                or response_position is None
            ):
                raise ValueError("response schema requires one reference branch")
            properties["topic_id"] = {"const": referenced.topic_id}
            properties["position"] = {"const": response_position}
            properties["relation"] = {"const": response_relation}
            properties["response_to_id"] = {"const": response_reference_id}
            properties["evidence_id"] = {"const": response_reference_id}
            required.extend(("topic_id", "position", "relation", "response_to_id", "evidence_id"))
        else:
            properties["topic_id"] = {"type": "string", "enum": topic_ids}
            properties["position"] = {
                "type": "string",
                "enum": ["support", "oppose", "undecided"],
            }
            properties["relation"] = {"const": "independent"}
            required.extend(("topic_id", "position", "relation"))
            evidence_ids = [item.id for item in observation.evidence_options.get(action.key, [])]
            if evidence_ids:
                properties["evidence_id"] = {"type": "string", "enum": evidence_ids}
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
            evidence_ids = _target_evidence_ids(
                observation,
                action_key=action.key,
                target_id=vote_target_id,
            )
            if evidence_ids:
                properties["evidence_id"] = {
                    "type": "string",
                    "enum": evidence_ids,
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
    observation: AgentObservation,
    *,
    action_key: str,
    target_id: str | None,
) -> list[str]:
    return [
        item.id
        for item in observation.evidence_options.get(action_key, [])
        if target_id in {item.actor_id, item.topic_id}
    ]


def _response_variants(
    observation: AgentObservation,
    action_key: str,
    reference_id: str,
) -> tuple[tuple[str, str], ...]:
    referenced = next(speech for speech in observation.speeches if speech.speech_id == reference_id)
    if referenced.position.value == "undecided":
        variants: list[tuple[str, str]] = [
            ("answer", "support"),
            ("answer", "oppose"),
            ("support", "undecided"),
        ]
    else:
        opposite = "oppose" if referenced.position.value == "support" else "support"
        variants = [("support", referenced.position.value), ("challenge", opposite)]
    prior = next(
        (
            speech
            for speech in reversed(observation.speeches)
            if speech.player_id == observation.me.id and speech.topic_id == referenced.topic_id
        ),
        None,
    )
    if prior is not None:
        variants.extend(
            ("revise", position)
            for position in ("support", "oppose", "undecided")
            if position != prior.position.value
        )
    allowed_relations = {
        relation.value for relation in observation.legal_relations.get(action_key, [])
    }
    return tuple(item for item in variants if item[0] in allowed_relations)


__all__ = ["build_decision_response_schema"]
