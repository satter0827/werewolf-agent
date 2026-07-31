"""公開Agent SDKとLLM decision pipelineを接続するadapter."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from hashlib import sha256

from werewolf_agent.adapters.llm.langchain.service import LangChainDecisionProvider
from werewolf_agent.adapters.llm.models import (
    AgentAbilityContext,
    AgentActionType,
    AgentAvailableAction,
    AgentDecision,
    AgentGameContext,
    AgentPhase,
    AgentPlayerStatus,
    AgentScenario,
    AgentSpeech,
    AgentVoteRound,
    PlayerProfile,
    VisiblePlayer,
)
from werewolf_agent.adapters.llm.models import (
    AgentObservation as LlmObservation,
)
from werewolf_agent.adapters.llm.tracing import LlmInvocationTrace, LlmTraceSink
from werewolf_agent.agents import (
    AgentContext,
    AgentDecisionError,
    AgentSession,
    AgentSpec,
    DecisionRequest,
    DecisionResponse,
)

_IMPLEMENTATION_VERSION = "1.1.0"
_FAILURE_CODE = "llm_decision_failed"


@dataclass(frozen=True)
class LangChainAgentFactory:
    """Fakeと実LLMを同じ公開Agent Session契約で生成する."""

    provider: LangChainDecisionProvider = field(repr=False)
    profile: PlayerProfile

    @property
    def spec(self) -> AgentSpec:
        """Credentialを含まない再現可能なLLM Agent identityを返す."""
        prompt_payload = self.provider.prompt.model_dump(mode="json", by_alias=True)
        decision_model = self.provider.decision_model
        parameters: dict[str, object] = {
            "provider": self.provider.provider_name,
            "model": self.provider.model_name,
            "decision_model_type": (
                f"{type(decision_model).__module__}.{type(decision_model).__qualname__}"
            ),
            "max_output_tokens": self.provider.max_output_tokens,
            "deliberation_level": self.provider.deliberation_level.value,
            "prompt_checksum": _checksum(prompt_payload),
            "profile": self.profile.model_dump(mode="json"),
        }
        for field_name in (
            "base_url",
            "timeout_seconds",
            "max_tokens",
            "temperature",
            "max_retries",
        ):
            value = getattr(decision_model, field_name, None)
            if value not in {None, ""}:
                parameters[field_name] = value
        fingerprint = _checksum(
            {
                "agent_id": "langchain",
                "implementation_version": _IMPLEMENTATION_VERSION,
                "parameters": parameters,
            }
        )
        return AgentSpec("langchain", _IMPLEMENTATION_VERSION, fingerprint, parameters)

    def create(self, context: AgentContext) -> AgentSession:
        """gameとplayerに分離したLLM Sessionを生成する."""
        capture = _TraceCapture(self.provider.trace_sink)
        provider = replace(self.provider, trace_sink=capture)
        return _LangChainAgentSession(context, provider, self.profile, capture)


@dataclass
class _LangChainAgentSession:
    context: AgentContext
    provider: LangChainDecisionProvider
    profile: PlayerProfile
    trace_capture: _TraceCapture
    closed: bool = field(default=False, init=False)

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        """公開入力をLLM DTOへ変換し、一回だけproviderを呼び出す."""
        if self.closed:
            raise RuntimeError("agent session is closed")
        if request.context != self.context:
            raise ValueError("request context does not belong to this session")
        self.trace_capture.last_trace = None
        try:
            decision = self.provider.choose_decision(
                self.context.player_id,
                _llm_observation(request, self.profile),
            )
            _require_legal_decision(request, decision)
        except AgentDecisionError:
            raise
        except Exception as exc:
            raise AgentDecisionError(
                _FAILURE_CODE,
                {"error_type": type(exc).__name__},
            ) from exc
        trace = self.trace_capture.last_trace
        if trace is not None and trace.fallback_used:
            diagnostics: dict[str, object] = {
                "provider": trace.provider,
                "model": trace.model,
                "validation_status": trace.validation_status,
            }
            if trace.provider_error:
                diagnostics["provider_error"] = trace.provider_error
            raise AgentDecisionError(_FAILURE_CODE, diagnostics)
        metadata = {"reason": decision.reason} if decision.reason else {}
        return DecisionResponse(
            action_type=decision.type.value,
            ability_id=decision.ability_id,
            target_id=decision.target_id,
            message=decision.message,
            focus_id=decision.focus_id,
            evidence_id=decision.evidence_id,
            metadata=metadata,
        )

    def close(self) -> None:
        """Sessionを冪等にcloseする."""
        self.closed = True


@dataclass
class _TraceCapture:
    delegate: LlmTraceSink | None = field(default=None, repr=False)
    last_trace: LlmInvocationTrace | None = field(default=None, init=False)

    def record_invocation(self, trace: LlmInvocationTrace) -> None:
        self.last_trace = trace
        if self.delegate is not None:
            self.delegate.record_invocation(trace)


def _llm_observation(request: DecisionRequest, profile: PlayerProfile) -> LlmObservation:
    observation = request.observation
    players = [
        VisiblePlayer(
            id=player.player_id,
            name=player.name,
            status=AgentPlayerStatus.ALIVE if player.alive else AgentPlayerStatus.DEAD,
        )
        for player in observation.players
    ]
    speeches: list[AgentSpeech] = []
    vote_rounds: list[AgentVoteRound] = []
    for event in request.public_timeline:
        if event.event_type == "speech" and event.actor_id is not None:
            message = event.payload.get("message")
            if isinstance(message, str) and message.strip():
                speeches.append(
                    AgentSpeech(
                        day=event.day,
                        player_id=event.actor_id,
                        message=message,
                        focus_id=_optional_text(event.payload.get("focus_id")),
                        evidence_id=_optional_text(event.payload.get("evidence_id")),
                    )
                )
        if event.event_type == "vote_round":
            vote_rounds.append(
                AgentVoteRound(
                    day=event.day,
                    votes=_text_mapping(event.payload.get("votes")),
                    counts=_count_mapping(event.payload.get("counts")),
                    eliminated_player_id=_optional_text(event.payload.get("eliminated_player_id")),
                )
            )
    world = observation.world
    identity = observation.identity
    game_context = None
    scenario = None
    if world is not None:
        scenario = AgentScenario(name=world.theme_name, premise=world.premise)
    if world is not None and identity is not None:
        game_context = AgentGameContext(
            theme_id=world.theme_id,
            theme_name=world.theme_name,
            premise=world.premise,
            role_id=identity.role_id,
            role_name=identity.role_name,
            identity_faction=identity.identity_faction_id,
            identity_faction_name=identity.identity_faction_name,
            victory_team=identity.victory_team_id,
            victory_team_name=identity.victory_team_name,
            objective=identity.objective,
            abilities=tuple(
                AgentAbilityContext(
                    id=ability.ability_id,
                    name=ability.name,
                    kind=ability.kind,
                    remaining_uses=ability.remaining_uses,
                )
                for ability in identity.abilities
            ),
            relevant_rules=dict(world.relevant_rules),
            action_names=dict(world.action_names),
            phase_names=dict(world.phase_names),
            setup_checksum=world.setup_checksum,
            mechanics_checksum=world.mechanics_checksum,
        )
    return LlmObservation(
        phase=AgentPhase(observation.phase),
        day=observation.day,
        decision_seed=request.decision_seed,
        me=next(player for player in players if player.id == observation.me.player_id),
        role=identity.role_id if identity is not None else None,
        profile=profile,
        scenario=scenario,
        game_context=game_context,
        players=players,
        known_roles=dict(observation.known_roles),
        known_factions=dict(observation.known_factions),
        available_actions=[
            AgentAvailableAction(
                type=AgentActionType(option.action_type),
                ability_id=option.ability_id,
            )
            for option in request.options
        ],
        legal_targets={option.key: list(option.legal_target_ids) for option in request.options},
        speeches=speeches,
        vote_rounds=vote_rounds,
    )


def _checksum(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _require_legal_decision(request: DecisionRequest, decision: AgentDecision) -> None:
    option = next(
        (
            item
            for item in request.options
            if item.action_type == decision.type.value and item.ability_id == decision.ability_id
        ),
        None,
    )
    if option is None:
        raise AgentDecisionError("llm_action_not_available")
    if decision.target_id is not None and decision.target_id not in option.legal_target_ids:
        raise AgentDecisionError("llm_target_not_legal")
    if option.legal_target_ids and decision.target_id is None:
        raise AgentDecisionError("llm_target_required")
    if decision.type is AgentActionType.SPEECH:
        if decision.message is None:
            raise AgentDecisionError("llm_message_required")
        if (
            option.message_max_chars is not None
            and len(decision.message) > option.message_max_chars
        ):
            raise AgentDecisionError("llm_message_too_long")
    elif decision.message is not None:
        raise AgentDecisionError("llm_message_not_allowed")


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _text_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if isinstance(item, str) and str(key).strip() and item.strip()
    }


def _count_mapping(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if isinstance(item, int) and not isinstance(item, bool) and str(key).strip()
    }


__all__ = ["LangChainAgentFactory"]
