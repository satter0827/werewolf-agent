"""LangChain-backed decision services for visible player observations."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Final

from langchain_core.language_models.fake import FakeListLLM
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.utils.json import parse_json_markdown

from werewolf_agent.commons.shared.definitions import FakeDecisionCatalog, PromptDefinition
from werewolf_agent.commons.shared.llm_tracing import LlmInvocationTrace, LlmTraceSink
from werewolf_agent.commons.shared.messages import (
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
from werewolf_agent.contracts import (
    ERROR_CONTEXT_LLM_BASE_URL,
    ERROR_CONTEXT_LLM_ERROR_TYPE,
    ERROR_CONTEXT_LLM_MAX_TOKENS,
    ERROR_CONTEXT_LLM_MODEL,
    ERROR_CONTEXT_LLM_PROVIDER,
    ERROR_CONTEXT_LLM_TIMEOUT_SECONDS,
)
from werewolf_agent.domain.llm.models import (
    AgentActionType,
    AgentDecision,
    AgentObservation,
    AgentPhase,
    AgentPlayerStatus,
    VisiblePlayer,
)

DETERMINISTIC_SELECTOR_BYTES: Final = 8
PROMPT_JSON_SEPARATORS: Final[tuple[str, str]] = (",", ":")
PROMPT_RECENT_SPEECH_LIMIT: Final = 3
PROMPT_RECENT_VOTE_ROUND_LIMIT: Final = 2
LLM_SPEECH_MESSAGE_MAX_CHARS: Final = 80


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
    trace_sink: LlmTraceSink | None = field(default=None, repr=False, compare=False)
    parser: PydanticOutputParser[AgentDecision] = field(
        default_factory=lambda: PydanticOutputParser(pydantic_object=AgentDecision)
    )

    def choose_decision(self, player_id: str, observation: AgentObservation) -> AgentDecision:
        """Return one validated decision from visible player context."""
        preflight_decision = _preflight_decision(player_id, observation)
        if preflight_decision is not None:
            return preflight_decision

        observation = observation.model_copy(
            update={"legal_targets": _legal_targets_by_action(observation)}
        )
        action_type = _selected_action(observation)
        target_id = _target_for_action(observation, action_type)
        if action_type in AgentDecision.TARGET_TYPES and target_id is None:
            return AgentDecision.pass_(
                player_id=player_id,
                reason=_missing_target_reason(action_type),
            )

        prompt_value = _to_chat_prompt(self.prompt).invoke(
            _prompt_inputs(
                player_id,
                observation,
                selected_action=action_type,
                parser=self.parser,
            )
        )
        prompt_messages = _prompt_messages(prompt_value)
        started = time.perf_counter()
        try:
            raw_output = self._invoke_model(
                prompt_value,
                action_type,
                player_id,
                target_id,
                observation,
            )
        except LlmModelInvocationError as exc:
            self._record_trace(
                player_id=player_id,
                observation=observation,
                prompt_messages=prompt_messages,
                request_payload=_trace_request_payload(action_type, target_id),
                error_payload=dict(exc.context),
                latency_ms=_elapsed_ms(started),
            )
            raise
        except Exception as exc:
            self._record_trace(
                player_id=player_id,
                observation=observation,
                prompt_messages=prompt_messages,
                request_payload=_trace_request_payload(action_type, target_id),
                error_payload={"error_type": type(exc).__name__},
                latency_ms=_elapsed_ms(started),
            )
            return AgentDecision.pass_(
                player_id=player_id,
                reason=message_invalid_llm_decision(type(exc).__name__),
            )

        try:
            decision = _parse_decision_output(
                raw_output,
                player_id=player_id,
                action_type=action_type,
                fallback_target_id=target_id,
                legal_target_ids=observation.legal_targets.get(action_type, []),
                parser=self.parser,
            )
        except Exception as exc:
            self._record_trace(
                player_id=player_id,
                observation=observation,
                prompt_messages=prompt_messages,
                request_payload=_trace_request_payload(action_type, target_id),
                raw_response=_json_mapping(raw_output),
                error_payload={"error_type": type(exc).__name__},
                latency_ms=_elapsed_ms(started),
            )
            return AgentDecision.pass_(
                player_id=player_id,
                reason=message_invalid_llm_decision(type(exc).__name__),
            )
        validated = _validated_decision(player_id, observation, decision)
        self._record_trace(
            player_id=player_id,
            observation=observation,
            prompt_messages=prompt_messages,
            request_payload=_trace_request_payload(action_type, target_id),
            raw_response=_json_mapping(raw_output),
            parsed_decision=validated.model_dump(mode="json"),
            latency_ms=_elapsed_ms(started),
        )
        return validated

    def _invoke_model(
        self,
        prompt_value: Any,
        action_type: AgentActionType,
        player_id: str,
        target_id: str | None,
        observation: AgentObservation,
    ) -> object:
        if self.fake_responses is not None:
            response = self.fake_responses.render(
                action_type.value,
                context=_fake_template_context(player_id, target_id, observation),
                selector=_fake_response_selector(player_id, action_type, target_id, observation),
            )
            return FakeListLLM(responses=[response]).invoke(prompt_value)
        if self.model is None:
            raise LlmModelInvocationError(
                MESSAGE_LLM_MODEL_NOT_CONFIGURED,
                context=self._invocation_error_context(MESSAGE_LLM_MODEL_NOT_CONFIGURED),
            )
        try:
            return self.model.invoke(prompt_value)
        except Exception as exc:
            error_type = type(exc).__name__
            raise LlmModelInvocationError(
                error_type,
                context=self._invocation_error_context(error_type),
            ) from exc

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
) -> Mapping[str, object]:
    payload: dict[str, object] = {"selected_action": action_type.value}
    if target_id is not None:
        payload["target_id"] = target_id
    return payload


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
    return round((time.perf_counter() - started) * 1000, 3)


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
    selector = _fake_target_selector(observation.me.id, observation, action_type)
    return candidates[selector % len(candidates)]


def _target_candidates(
    observation: AgentObservation,
    action_type: AgentActionType,
) -> list[str]:
    alive_players = [
        player.id for player in observation.players if player.status is AgentPlayerStatus.ALIVE
    ]
    if action_type in {AgentActionType.VOTE, AgentActionType.SEER_INSPECT}:
        return [player_id for player_id in alive_players if player_id != observation.me.id]
    if action_type is AgentActionType.WEREWOLF_ATTACK:
        attacker_role = observation.role
        return [
            player_id
            for player_id in alive_players
            if player_id != observation.me.id
            and (attacker_role is None or observation.known_roles.get(player_id) != attacker_role)
        ]
    if action_type is AgentActionType.KNIGHT_GUARD:
        return alive_players
    return []


def _legal_targets_by_action(
    observation: AgentObservation,
) -> dict[AgentActionType, list[str]]:
    """Return legal target ids for available target-taking actions."""
    targets: dict[AgentActionType, list[str]] = {}
    for action_type in observation.available_actions:
        if action_type not in AgentDecision.TARGET_TYPES:
            continue
        configured_targets = observation.legal_targets.get(action_type)
        targets[action_type] = (
            list(configured_targets)
            if configured_targets is not None
            else _target_candidates(observation, action_type)
        )
    return targets


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


def _fake_response_selector(
    player_id: str,
    action_type: AgentActionType,
    target_id: str | None,
    observation: AgentObservation,
) -> int:
    digest = sha256(
        (
            f"{player_id}:{action_type.value}:{target_id or ''}:"
            f"{observation.day}:{len(observation.speeches)}:{len(observation.vote_rounds)}"
        ).encode()
    ).digest()
    return int.from_bytes(digest[:DETERMINISTIC_SELECTOR_BYTES], "big")


def _fake_target_selector(
    player_id: str,
    observation: AgentObservation,
    action_type: AgentActionType,
) -> int:
    digest = sha256(f"{player_id}:{action_type.value}:{observation.day}:target".encode()).digest()
    return int.from_bytes(digest[:DETERMINISTIC_SELECTOR_BYTES], "big")


def _fake_template_context(
    player_id: str,
    target_id: str | None,
    observation: AgentObservation,
) -> dict[str, str]:
    target = next((player for player in observation.players if player.id == target_id), None)
    focus = _focus_player(observation)
    profile = observation.profile
    return {
        "player_id": player_id,
        "player_name": observation.me.name,
        "target_id": target_id or "",
        "target_name": target.name if target is not None else "",
        "focus_id": focus.id if focus is not None else "",
        "focus_name": focus.name if focus is not None else "",
        "day": str(observation.day),
        "phase": observation.phase.value,
        "role": observation.role or "",
        "persona": _persona_text(profile),
        "character_profile": _character_profile_text(profile),
        "scenario_name": observation.scenario.name if observation.scenario is not None else "",
        "scenario_premise": (
            observation.scenario.premise if observation.scenario is not None else ""
        ),
        "profile_name": profile.name if profile is not None else observation.me.name,
    }


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
    selector = _fake_target_selector(
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
            _compact_observation(observation),
            ensure_ascii=False,
            separators=PROMPT_JSON_SEPARATORS,
        ),
        "format_instructions": _decision_format_instructions(),
    }


def _compact_observation(observation: AgentObservation) -> dict[str, object]:
    return {
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


def _decision_format_instructions() -> str:
    return (
        'Return JSON with keys "type", optional "target_id", optional "message", '
        'and optional "reason". Do not include "player_id"; the server sets it. '
        'Use the selected_action value as "type". Include "message" only for speech. '
        "Do not wrap the JSON in markdown fences. "
        f"Speech message must be {LLM_SPEECH_MESSAGE_MAX_CHARS} characters or less."
    )


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
