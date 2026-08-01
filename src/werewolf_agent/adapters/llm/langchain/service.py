"""Explicit decision pipeline shared by fake and real chat-model adapters."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, cast

from werewolf_agent.adapters.llm.definitions import PromptDefinition
from werewolf_agent.adapters.llm.langchain.constants import (
    LLM_SPEECH_MESSAGE_MAX_CHARS,
    SECONDS_TO_MILLISECONDS,
    VALIDATION_STATUS_FALLBACK,
    VALIDATION_STATUS_VALID,
)
from werewolf_agent.adapters.llm.langchain.decisions import (
    _fallback_decision,
    _legal_targets_by_action,
)
from werewolf_agent.adapters.llm.messages import message_invalid_llm_decision
from werewolf_agent.adapters.llm.model_adapters import LlmModelInvocationError
from werewolf_agent.adapters.llm.models import (
    AgentActionType,
    AgentDecision,
    AgentModelDecision,
    AgentObservation,
    AgentPhase,
    AgentPlayerStatus,
    DecisionTask,
    DeliberationLevel,
    ModelMessage,
    ModelRequest,
    ModelResponse,
)
from werewolf_agent.adapters.llm.ports import DecisionModel
from werewolf_agent.adapters.llm.tracing import LlmInvocationTrace, LlmTraceSink

PIPELINE_REVISION = "decision-v3"
CompiledPromptMessage = tuple[Literal["system", "human", "ai"], str, str, bool]


@dataclass(frozen=True)
class LangChainDecisionProvider:
    """Turn one authorized observation into a validated game decision."""

    prompt: PromptDefinition
    decision_model: DecisionModel
    provider_name: str
    model_name: str
    max_output_tokens: int
    deliberation_level: DeliberationLevel = DeliberationLevel.STANDARD
    trace_sink: LlmTraceSink | None = field(default=None, repr=False, compare=False)
    _compiled_messages: tuple[CompiledPromptMessage, ...] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        """Compile static prompt fragments once for this provider."""
        object.__setattr__(self, "_compiled_messages", _compile_prompt(self.prompt))

    def choose_decision(self, player_id: str, observation: AgentObservation) -> AgentDecision:
        """Run the bounded decision pipeline once."""
        preflight = _preflight_decision(player_id, observation)
        if preflight is not None:
            return preflight
        normalized = observation.model_copy(
            update={"legal_targets": _legal_targets_by_action(observation)}
        )
        if (
            len(normalized.available_actions) == 1
            and normalized.available_actions[0].type is AgentActionType.PASS
        ):
            return AgentDecision.pass_(player_id, reason="only legal action")

        started_at = time.perf_counter()
        deliberation = self.prompt.deliberation[self.deliberation_level.value]
        context = _decision_context(
            player_id,
            normalized,
            event_limit=deliberation.event_limit,
        )
        context_text = json.dumps(
            context,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        context_checksum = hashlib.sha256(context_text.encode("utf-8")).hexdigest()
        messages = _render_prompt(self._compiled_messages, context_text)
        prompt_checksum = _messages_checksum(messages)
        task = DecisionTask(
            player_id=player_id,
            observation=normalized,
            deliberation_level=self.deliberation_level,
            output_token_limit=min(deliberation.output_token_limit, self.max_output_tokens),
            context=context,
            context_checksum=context_checksum,
        )
        request = ModelRequest(
            task=task,
            messages=messages,
            response_schema=AgentModelDecision.model_json_schema(),
            prompt_checksum=prompt_checksum,
        )

        response: ModelResponse | None = None
        error_payload: Mapping[str, object] | None = None
        try:
            response = self.decision_model.invoke(request)
            model_decision = _parse_model_decision(response.content)
            decision = _validated_decision(player_id, normalized, model_decision, context)
            validation_status = VALIDATION_STATUS_VALID
            fallback_reason = ""
        except LlmModelInvocationError as exc:
            error_payload = dict(exc.context) or {"error_type": exc.error_type}
            fallback_reason = message_invalid_llm_decision(exc.error_type)
            decision = _fallback(player_id, normalized, context_checksum, fallback_reason)
            validation_status = VALIDATION_STATUS_FALLBACK
        except Exception as exc:
            error_payload = {
                "validation_error": type(exc).__name__,
                "validation_detail": str(exc),
            }
            fallback_reason = message_invalid_llm_decision(type(exc).__name__)
            decision = _fallback(player_id, normalized, context_checksum, fallback_reason)
            validation_status = VALIDATION_STATUS_FALLBACK

        self._record_trace(
            player_id=player_id,
            observation=normalized,
            request=request,
            response=response,
            decision=decision,
            validation_status=validation_status,
            fallback_reason=fallback_reason,
            error_payload=error_payload,
            latency_ms=round(
                (time.perf_counter() - started_at) * SECONDS_TO_MILLISECONDS,
                3,
            ),
        )
        return decision

    def _record_trace(
        self,
        *,
        player_id: str,
        observation: AgentObservation,
        request: ModelRequest,
        response: ModelResponse | None,
        decision: AgentDecision,
        validation_status: str,
        fallback_reason: str,
        error_payload: Mapping[str, object] | None,
        latency_ms: float,
    ) -> None:
        if self.trace_sink is None:
            return
        prompt_messages: list[Mapping[str, object]] = [
            message.model_dump(mode="json") for message in request.messages
        ]
        prompt_text = json.dumps(prompt_messages, ensure_ascii=False, separators=(",", ":"))
        raw_response = response.model_dump(mode="json") if response is not None else None
        response_text = response.content if response is not None else ""
        usage = response.usage if response is not None else {}
        evidence_id, focus_id = _response_annotations(response)
        self.trace_sink.record_invocation(
            LlmInvocationTrace(
                provider=response.provider if response is not None else self.provider_name,
                model=response.model if response is not None else self.model_name,
                player_id=player_id,
                phase=observation.phase.value,
                day=observation.day,
                prompt_messages=prompt_messages,
                prompt_hash=request.prompt_checksum,
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
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
                request_payload={
                    "pipeline_revision": PIPELINE_REVISION,
                    "normalization": _normalization_status(response),
                    "stage": "validated"
                    if validation_status == VALIDATION_STATUS_VALID
                    else "fallback",
                    "validation_status": validation_status,
                    "fallback_reason": fallback_reason,
                    "deliberation_level": self.deliberation_level.value,
                    "decision_type": decision.type.value,
                    "risk_tolerance": (
                        observation.profile.risk_tolerance
                        if observation.profile is not None
                        else ""
                    ),
                    "evidence_focus": (
                        observation.profile.evidence_focus
                        if observation.profile is not None
                        else ""
                    ),
                    "focus_id": focus_id,
                    "evidence_id": evidence_id,
                },
                raw_response=raw_response,
                parsed_decision=decision.model_dump(mode="json"),
                error_payload=error_payload,
                latency_ms=latency_ms,
                validation_status=validation_status,
                fallback_used=validation_status == VALIDATION_STATUS_FALLBACK,
                fallback_reason=fallback_reason,
                provider_error=_provider_error(error_payload),
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                total_tokens=usage.get("total_tokens"),
                usage_source="usage_metadata" if usage else "unavailable",
                prompt_characters=len(prompt_text),
                prompt_bytes=len(prompt_text.encode("utf-8")),
                response_characters=len(response_text),
                response_bytes=len(response_text.encode("utf-8")),
            )
        )


def _preflight_decision(
    player_id: str,
    observation: AgentObservation,
) -> AgentDecision | None:
    if observation.me.id != player_id:
        return AgentDecision.pass_(player_id, reason="observation belongs to another player")
    if observation.me.status is not AgentPlayerStatus.ALIVE:
        return AgentDecision.pass_(player_id, reason="player is not alive")
    if not observation.available_actions:
        return AgentDecision.pass_(player_id, reason="no action is available")
    return None


def _decision_context(
    player_id: str,
    observation: AgentObservation,
    *,
    event_limit: int,
) -> dict[str, object]:
    game = observation.game_context
    actions = list(observation.available_actions)
    legal_reference_ids = {
        reference_id
        for action in actions
        for reference_id in observation.legal_references.get(action.key, [])
    }
    reference_speeches = {
        speech.speech_id: {
            "player_id": speech.player_id,
            "message": speech.message,
            "focus_id": speech.focus_id,
            "evidence_id": speech.evidence_id,
        }
        for speech in observation.speeches
        if speech.speech_id in legal_reference_ids
    }
    context: dict[str, object] = {
        "phase": observation.phase.value,
        "day": observation.day,
        "seed": observation.decision_seed,
        "me": {
            "id": player_id,
            "name": observation.me.name,
            "role": game.role_name if game is not None else observation.role,
            "objective": game.objective if game is not None else "",
        },
        "profile": _profile_context(observation),
        "legal": {
            "actions": [action.key for action in actions],
            "targets": {
                action.key: list(observation.legal_targets.get(action.key, []))
                for action in actions
                if action.type in AgentDecision.TARGET_TYPES
            },
            "references": {
                action.key: list(observation.legal_references.get(action.key, []))
                for action in actions
                if observation.legal_references.get(action.key)
            },
            "reference_speeches": reference_speeches,
            "constraints": {
                "speech_max_chars": LLM_SPEECH_MESSAGE_MAX_CHARS,
                "target_required_for": [
                    action.key for action in actions if action.type in AgentDecision.TARGET_TYPES
                ],
                "message_required_for": [AgentActionType.SPEECH.value]
                if any(action.type is AgentActionType.SPEECH for action in actions)
                else [],
                "response_to_required_for": [
                    action.key for action in actions if observation.legal_references.get(action.key)
                ],
            },
        },
        "players": [
            {"id": player.id, "name": player.name, "status": player.status.value}
            for player in observation.players
        ],
        "known": {
            "roles": dict(observation.known_roles),
            "factions": dict(observation.known_factions),
        },
        "public_position": {
            "current_suspicion_id": _current_suspicion_id(observation),
        },
        "candidate_signals": _candidate_signals(observation),
        "evidence": _evidence(observation, event_limit=event_limit),
    }
    if game is not None:
        context["setting"] = {
            "theme": game.theme_name,
            "premise": game.premise if observation.phase is AgentPhase.DAY_DISCUSSION else "",
            "actions": {
                action.key: game.action_names.get(action.type.value, action.key)
                for action in actions
            },
            "abilities": [
                {
                    "id": ability.id,
                    "name": ability.name,
                    "remaining_uses": ability.remaining_uses,
                }
                for ability in game.abilities
                if any(action.ability_id == ability.id for action in actions)
            ],
        }
    return context


def _profile_context(observation: AgentObservation) -> dict[str, object]:
    profile = observation.profile
    if profile is None:
        return {}
    return {
        "personality": profile.personality,
        "speaking_style": profile.speaking_style,
        "reasoning_style": profile.reasoning_style,
        "risk_tolerance": profile.risk_tolerance,
        "evidence_focus": profile.evidence_focus,
    }


def _candidate_signals(observation: AgentObservation) -> dict[str, dict[str, int]]:
    """Return public comparison signals without selecting or ordering a target."""
    target_ids = {
        player_id
        for action in observation.available_actions
        for player_id in observation.legal_targets.get(action.key, [])
    }
    latest_counts = observation.vote_rounds[-1].counts if observation.vote_rounds else {}
    speech_counts: dict[str, int] = {}
    for speech in observation.speeches:
        speech_counts[speech.player_id] = speech_counts.get(speech.player_id, 0) + 1
    return {
        player_id: {
            "previous_votes": int(latest_counts.get(player_id, 0)),
            "public_speeches": speech_counts.get(player_id, 0),
        }
        for player_id in sorted(target_ids)
    }


def _current_suspicion_id(observation: AgentObservation) -> str | None:
    """Return the player's latest public speech focus or resolved vote target."""
    for speech in reversed(observation.speeches):
        if speech.player_id == observation.me.id and speech.focus_id is not None:
            return speech.focus_id
    for vote_round in reversed(observation.vote_rounds):
        target_id = vote_round.votes.get(observation.me.id)
        if target_id is not None:
            return target_id
    return None


def _evidence(observation: AgentObservation, *, event_limit: int) -> list[dict[str, object]]:
    ordered_events: list[tuple[int, int, int, dict[str, object]]] = []
    previous_speech_by_player: dict[str, str] = {}
    for index, speech in enumerate(observation.speeches):
        previous_message = previous_speech_by_player.get(speech.player_id)
        previous_speech_by_player[speech.player_id] = speech.message
        ordered_events.append(
            (
                speech.day,
                0,
                index,
                {
                    "id": speech.speech_id,
                    "type": "my_speech" if speech.player_id == observation.me.id else "speech",
                    "day": speech.day,
                    "player_id": speech.player_id,
                    "message": speech.message,
                    "focus_id": speech.focus_id,
                    "evidence_id": speech.evidence_id,
                    "response_to_id": speech.response_to_id,
                    "changed": (
                        previous_message is not None and previous_message != speech.message
                    ),
                },
            )
        )
    for round_index, vote_round in enumerate(observation.vote_rounds):
        for vote_index, (voter_id, target_id) in enumerate(vote_round.votes.items()):
            ordered_events.append(
                (
                    vote_round.day,
                    1 + round_index * 2,
                    vote_index,
                    {
                        "id": f"vote:d{vote_round.day}:r{round_index + 1}:{voter_id}",
                        "type": "my_vote" if voter_id == observation.me.id else "vote",
                        "day": vote_round.day,
                        "player_id": voter_id,
                        "target_id": target_id,
                    },
                )
            )
        ordered_events.append(
            (
                vote_round.day,
                2 + round_index * 2,
                0,
                {
                    "id": f"vote_result:d{vote_round.day}:r{round_index + 1}",
                    "type": "vote_result",
                    "day": vote_round.day,
                    "counts": dict(vote_round.counts),
                    "eliminated_player_id": vote_round.eliminated_player_id,
                },
            )
        )
    ordered_events.sort(key=lambda item: item[:3])
    return [event for *_, event in ordered_events[-event_limit:]]


def _compile_prompt(prompt: PromptDefinition) -> tuple[CompiledPromptMessage, ...]:
    marker = "{{decision_context_json}}"
    marker_count = sum(message.content.count(marker) for message in prompt.messages)
    if marker_count != 1:
        raise ValueError("prompt must contain decision_context_json exactly once")
    compiled: list[CompiledPromptMessage] = []
    for message in prompt.messages:
        prefix, separator, suffix = message.content.partition(marker)
        if not separator:
            prefix, suffix = message.content, ""
        compiled.append(
            (
                cast(Literal["system", "human", "ai"], message.role),
                prefix,
                suffix,
                bool(separator),
            )
        )
    return tuple(compiled)


def _render_prompt(
    compiled_messages: tuple[CompiledPromptMessage, ...], context_text: str
) -> tuple[ModelMessage, ...]:
    return tuple(
        ModelMessage(role=role, content=f"{prefix}{context_text if dynamic else ''}{suffix}")
        for role, prefix, suffix, dynamic in compiled_messages
    )


def _messages_checksum(messages: tuple[ModelMessage, ...]) -> str:
    payload = json.dumps(
        [message.model_dump(mode="json") for message in messages],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_model_decision(content: str) -> AgentModelDecision:
    normalized = _normalize_json_response(content)
    parsed = json.loads(normalized)
    return AgentModelDecision.model_validate(parsed)


def _normalize_json_response(content: str) -> str:
    """Remove one complete Markdown fence without repairing response content."""
    normalized = content.strip()
    if not normalized.startswith("```"):
        return normalized
    lines = normalized.splitlines()
    if len(lines) < 3 or lines[-1].strip() != "```":
        raise ValueError("incomplete Markdown fence")
    opening = lines[0].strip().lower()
    if opening not in {"```", "```json"}:
        raise ValueError("unsupported Markdown fence")
    return "\n".join(lines[1:-1]).strip()


def _normalization_status(response: ModelResponse | None) -> str:
    if response is None:
        return "not_applicable"
    content = response.content.strip()
    if not content.startswith("```"):
        return "none"
    try:
        _normalize_json_response(content)
    except ValueError:
        return "failed"
    return "markdown_fence_removed"


def _validated_decision(
    player_id: str,
    observation: AgentObservation,
    model_decision: AgentModelDecision,
    context: Mapping[str, object],
) -> AgentDecision:
    requested_key = (
        f"{model_decision.type.value}:{model_decision.ability_id}"
        if model_decision.ability_id
        else model_decision.type.value
    )
    available_keys = {action.key for action in observation.available_actions}
    if requested_key not in available_keys:
        raise ValueError("action is not available")
    if model_decision.type in AgentDecision.TARGET_TYPES:
        legal_targets = observation.legal_targets.get(requested_key, [])
        if model_decision.target_id not in legal_targets:
            raise ValueError("target is not legal")
    if model_decision.type is AgentActionType.VOTE and not model_decision.reason.strip():
        raise ValueError("vote requires a public reason")
    legal_references = observation.legal_references.get(requested_key, [])
    if legal_references and model_decision.response_to_id is None:
        raise ValueError("response speech requires a reference")
    if (
        model_decision.response_to_id is not None
        and model_decision.response_to_id not in legal_references
    ):
        raise ValueError("speech reference is not legal")
    visible_ids = {player.id for player in observation.players}
    if model_decision.focus_id is not None and (
        model_decision.focus_id not in visible_ids or model_decision.focus_id == player_id
    ):
        raise ValueError("focus is not visible")
    evidence_value = context.get("evidence")
    evidence = evidence_value if isinstance(evidence_value, list) else []
    evidence_ids = {
        str(item["id"]) for item in evidence if isinstance(item, Mapping) and item.get("id")
    }
    if model_decision.evidence_id is not None and model_decision.evidence_id not in evidence_ids:
        raise ValueError("evidence is not visible")
    if (
        model_decision.type is AgentActionType.SPEECH
        and model_decision.message is not None
        and len(model_decision.message) > LLM_SPEECH_MESSAGE_MAX_CHARS
    ):
        raise ValueError("speech is too long")
    return AgentDecision(
        type=model_decision.type,
        player_id=player_id,
        ability_id=model_decision.ability_id,
        target_id=model_decision.target_id,
        message=model_decision.message,
        focus_id=model_decision.focus_id,
        evidence_id=model_decision.evidence_id,
        response_to_id=model_decision.response_to_id,
        reason=model_decision.reason,
    )


def _fallback(
    player_id: str,
    observation: AgentObservation,
    context_checksum: str,
    reason: str,
) -> AgentDecision:
    actions = observation.available_actions
    if not actions:
        return AgentDecision.pass_(player_id, reason=reason)
    selector = int(context_checksum[:16], 16)
    action = actions[selector % len(actions)]
    return _fallback_decision(player_id, observation, action, reason=reason)


def _response_annotations(response: ModelResponse | None) -> tuple[str | None, str | None]:
    if response is None:
        return None, None
    try:
        parsed = json.loads(_normalize_json_response(response.content))
    except Exception:
        return None, None
    if not isinstance(parsed, Mapping):
        return None, None
    evidence_id = str(parsed.get("evidence_id") or "").strip() or None
    focus_id = str(parsed.get("focus_id") or "").strip() or None
    return evidence_id, focus_id


def _provider_error(error_payload: Mapping[str, object] | None) -> str:
    if not error_payload or set(error_payload) <= {"validation_error", "validation_detail"}:
        return ""
    return str(
        error_payload.get("llm_error_type") or error_payload.get("error_type") or "provider_error"
    )


__all__ = ["LangChainDecisionProvider", "LlmModelInvocationError"]
