"""LangChain-backed decision services for visible player observations."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping
from hashlib import sha256
from typing import Any

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from werewolf_agent.adapters.llm.langchain.constants import (
    LLM_SPEECH_MESSAGE_MAX_CHARS,
    PROMPT_JSON_SEPARATORS,
    PROMPT_RECENT_SPEECH_LIMIT,
    PROMPT_RECENT_VOTE_ROUND_LIMIT,
    SECONDS_TO_MILLISECONDS,
)
from werewolf_agent.adapters.llm.langchain.decisions import (
    _legal_targets_by_action,
)
from werewolf_agent.agents.definitions import (
    PromptDefinition,
    PromptMessageDefinition,
)
from werewolf_agent.agents.models import (
    AgentActionType,
    AgentDecision,
    AgentObservation,
)


def _to_chat_prompt(prompt: PromptDefinition) -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [(message.role, _langchain_content(message)) for message in prompt.messages]
    )


def _langchain_content(message: PromptMessageDefinition) -> str:
    """Convert portable double-brace variables at the LangChain boundary."""
    return re.sub(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}", r"{\1}", message.content)


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
        "graph_revision": str(state.get("graph_revision") or ""),
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
    game_context = observation.game_context
    return {
        "player_id": player_id,
        "phase": (
            game_context.phase_names.get(observation.phase.value, observation.phase.value)
            if game_context is not None
            else observation.phase.value
        ),
        "day": str(observation.day),
        "role": (
            game_context.role_name
            if game_context is not None
            else observation.role
            if observation.role is not None
            else ""
        ),
        "scenario_name": observation.scenario.name if observation.scenario is not None else "",
        "scenario_premise": (
            observation.scenario.premise if observation.scenario is not None else ""
        ),
        "character_profile": _character_profile_text(observation.profile),
        "game_context_json": json.dumps(
            (game_context.model_dump(mode="json") if game_context is not None else {}),
            ensure_ascii=False,
            separators=PROMPT_JSON_SEPARATORS,
            sort_keys=True,
        ),
        "available_actions": json.dumps(
            [action.value for action in observation.available_actions],
            ensure_ascii=False,
        ),
        "selected_action": selected_action.value,
        "role_hint": role_hint,
        "target_rankings_json": json.dumps(
            dict(target_rankings or {}),
            ensure_ascii=False,
            separators=PROMPT_JSON_SEPARATORS,
        ),
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
        "known_factions": dict(observation.known_factions),
        "speeches": [
            speech.model_dump(mode="json")
            for speech in observation.speeches[-PROMPT_RECENT_SPEECH_LIMIT:]
        ],
        "vote_rounds": [
            vote_round.model_dump(mode="json")
            for vote_round in observation.vote_rounds[-PROMPT_RECENT_VOTE_ROUND_LIMIT:]
        ],
    }
    if observation.game_context is not None:
        payload["game_context"] = observation.game_context.model_dump(mode="json")
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
