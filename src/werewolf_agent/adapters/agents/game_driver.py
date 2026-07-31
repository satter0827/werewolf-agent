"""Automated-player driver connecting agents and application operations."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from importlib import import_module
from typing import Any, Protocol

import httpx

from werewolf_agent.adapters.agents.constants import (
    LLM_MODEL_AUTO,
    LLM_PROVIDER_FAKE,
    LLM_PROVIDER_LMSTUDIO,
    LLM_PROVIDER_OPENAI,
    LLM_STUDIO_API_KEY_PLACEHOLDER,
)
from werewolf_agent.adapters.agents.game_context import (
    agent_metadata_from_game_context,
    build_agent_game_contexts,
)
from werewolf_agent.adapters.agents.messages import (
    message_langchain_openai_required,
    message_unsupported_llm_provider,
)
from werewolf_agent.adapters.llm.agent import LangChainAgentFactory
from werewolf_agent.adapters.llm.configuration import LlmProviderConfig
from werewolf_agent.adapters.llm.langchain.constants import LLM_SPEECH_MESSAGE_MAX_CHARS
from werewolf_agent.adapters.llm.langchain.service import (
    LangChainDecisionProvider,
)
from werewolf_agent.adapters.llm.model_adapters import (
    FakeDecisionModel,
    LangChainChatDecisionModel,
)
from werewolf_agent.adapters.llm.models import (
    AgentGameContext,
    DeliberationLevel,
    PlayerProfile,
)
from werewolf_agent.adapters.llm.tracing import LlmTraceSink, NullLlmTraceSink
from werewolf_agent.adapters.resources import LlmDefinitions
from werewolf_agent.agents import (
    AgentContext,
    AgentDecisionError,
    AgentFactory,
    AgentObservation,
    DecisionOption,
    DecisionRequest,
    DecisionResponse,
    DecisionTrace,
    HeuristicAgentFactory,
    ObservedPlayer,
    PublicTimelineEvent,
)
from werewolf_agent.application.handlers import (
    commit_prepared_advance,
    prepare_advance_game,
    run_prepared_advance,
)
from werewolf_agent.application.models import (
    AdvanceGameCommand,
    AdvanceGameResult,
    ApplicationContext,
    PreparedAdvanceGame,
)
from werewolf_agent.contracts import (
    ERROR_CONTEXT_LLM_BASE_URL,
    ERROR_CONTEXT_LLM_ERROR_TYPE,
    ERROR_CONTEXT_LLM_PROVIDER,
    ERROR_CONTEXT_LLM_TIMEOUT_SECONDS,
    LLM_PROVIDER_ERROR_INVALID_MODELS_RESPONSE,
    LLM_PROVIDER_ERROR_NO_LOADED_MODEL,
    LlmProviderError,
)
from werewolf_agent.domain import Action, GameView

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentRuntime:
    """Dependencies used only while an adapter drives automated players."""

    config: LlmProviderConfig
    definitions: LlmDefinitions
    trace_sink: LlmTraceSink = field(default_factory=NullLlmTraceSink)
    agent_factories: Mapping[str, AgentFactory] = field(default_factory=dict)
    decision_trace_sink: DecisionTraceSink = field(default_factory=lambda: NullDecisionTraceSink())


class DecisionTraceSink(Protocol):
    """一回のAgent意思決定traceを受け取る外部adapter境界."""

    def record_decision(self, trace: DecisionTrace) -> None:
        """Chain-of-thoughtを含まない意思決定traceを保存する."""


class NullDecisionTraceSink:
    """Decision traceを破棄する既定sink."""

    def record_decision(self, trace: DecisionTrace) -> None:
        """何も保存しない."""
        _ = trace


def advance_game(
    context: ApplicationContext,
    command: AdvanceGameCommand,
    *,
    runtime: AgentRuntime,
) -> AdvanceGameResult:
    """Drive automated players, advance the domain, and commit the result."""
    prepared = prepare_advance_game(command, dependencies=context)
    driven = drive_prepared_game(
        prepared,
        runtime=runtime,
    )
    computed = run_prepared_advance(driven, dependencies=context)
    return commit_prepared_advance(computed, dependencies=context)


def drive_prepared_game(
    prepared: PreparedAdvanceGame,
    *,
    runtime: AgentRuntime,
) -> PreparedAdvanceGame:
    """Generate automated actions without placing agent logic in application."""
    game = prepared.game
    snapshot = game.snapshot()
    manual_player_ids = {
        str(player_id)
        for player_id, agent_type in dict(prepared.config.get("player_agent_types") or {}).items()
        if str(agent_type) == "manual"
    }
    profile_ids = {
        str(player_id): str(profile_id)
        for player_id, profile_id in dict(prepared.config.get("player_profile_ids") or {}).items()
    }
    game_contexts = _agent_game_contexts(prepared, snapshot)
    profiles: dict[str, PlayerProfile] | None = None
    provider: LangChainDecisionProvider | None = None
    events = []
    for index, player in enumerate(snapshot.players.values()):
        if player.status.value != "alive" or player.id in manual_player_ids:
            continue
        observation = game.view_for(player.id)
        if not observation.available_actions:
            continue
        decision_seed = (prepared.seed or 0) + prepared.version * 1009 + index * 131
        factory = runtime.agent_factories.get(player.id)
        if factory is None:
            if profiles is None:
                profiles = _profiles_from_config(prepared.config)
            if provider is None:
                provider = _decision_provider(
                    runtime.config,
                    definitions=runtime.definitions,
                    trace_sink=runtime.trace_sink,
                    deliberation_level=DeliberationLevel(
                        str(prepared.config["deliberation_level"])
                    ),
                )
            factory = LangChainAgentFactory(
                provider=provider,
                profile=_profile_for_player(
                    player.id,
                    seed=decision_seed,
                    profiles=profiles,
                    profile_ids_by_player=profile_ids,
                ),
            )
        context = AgentContext(
            session_id=f"{prepared.game_id}:{prepared.version}:{player.id}",
            game_id=prepared.game_id,
            player_id=player.id,
            session_seed=decision_seed,
        )
        request = _decision_request_from_game(
            context,
            observation,
            game_context=game_contexts.get(player.id),
            decision_seed=decision_seed,
        )
        action = _decide_action(
            factory,
            context,
            request,
            trace_sink=runtime.decision_trace_sink,
        )
        events.extend(game.submit(action))
        snapshot = game.snapshot()
        logger.debug(
            "game.agent_action.generated",
            extra={
                "event_action": "game.agent_action.generated",
                "game_phase": snapshot.phase.value,
                "game_day": snapshot.day,
                "game_version": prepared.version,
                "agent_type": "llm",
            },
        )
    return replace(prepared, domain_events=tuple(events))


def langchain_agent_factory(
    config: LlmProviderConfig,
    *,
    definitions: LlmDefinitions,
    profile: PlayerProfile,
    trace_sink: LlmTraceSink | None = None,
    deliberation_level: DeliberationLevel = DeliberationLevel.STANDARD,
) -> LangChainAgentFactory:
    """Return a LangChain-backed agent factory from application settings."""
    return LangChainAgentFactory(
        provider=_decision_provider(
            config,
            definitions=definitions,
            trace_sink=trace_sink,
            deliberation_level=deliberation_level,
        ),
        profile=profile,
    )


def _profile_for_player(
    player_id: str,
    *,
    seed: int,
    profiles: Mapping[str, PlayerProfile],
    profile_ids_by_player: Mapping[str, str],
) -> PlayerProfile:
    profile_id = profile_ids_by_player.get(player_id)
    if profile_id is None or profile_id not in profiles:
        profile_ids = sorted(profiles)
        profile_id = profile_ids[seed % len(profile_ids)]
    return profiles[profile_id]


def _profiles_from_config(config: Mapping[str, object]) -> dict[str, PlayerProfile]:
    value = config.get("player_profiles")
    if not isinstance(value, dict):
        raise ValueError("player_profiles are required in normalized game config")
    return {
        str(player_id): PlayerProfile.model_validate(profile)
        for player_id, profile in value.items()
    }


def _decision_provider(
    config: LlmProviderConfig,
    *,
    definitions: LlmDefinitions,
    trace_sink: LlmTraceSink | None,
    deliberation_level: DeliberationLevel,
) -> LangChainDecisionProvider:
    if config.provider == LLM_PROVIDER_FAKE:
        fake_model = FakeDecisionModel(catalog=definitions.fake_responses)
        return LangChainDecisionProvider(
            prompt=definitions.prompt,
            decision_model=fake_model,
            provider_name=config.provider,
            model_name=fake_model.model_name,
            max_output_tokens=config.max_tokens,
            trace_sink=trace_sink,
            deliberation_level=deliberation_level,
        )
    if config.provider in {LLM_PROVIDER_LMSTUDIO, LLM_PROVIDER_OPENAI}:
        model_id = _openai_compatible_model_id(config)
        chat_model = LangChainChatDecisionModel(
            model=_openai_compatible_model(config, model_id=model_id),
            provider_name=config.provider,
            model_name=model_id,
            base_url=config.base_url,
            timeout_seconds=config.timeout_seconds,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            max_retries=config.max_retries,
        )
        return LangChainDecisionProvider(
            prompt=definitions.prompt,
            decision_model=chat_model,
            provider_name=config.provider,
            model_name=model_id,
            max_output_tokens=config.max_tokens,
            trace_sink=trace_sink,
            deliberation_level=deliberation_level,
        )
    raise ValueError(message_unsupported_llm_provider(config.provider))


def _openai_compatible_model(config: LlmProviderConfig, *, model_id: str) -> Any:
    try:
        module = import_module("langchain_openai")
    except ImportError as exc:
        raise LlmProviderError(
            message_langchain_openai_required(
                lmstudio_provider=LLM_PROVIDER_LMSTUDIO,
                openai_provider=LLM_PROVIDER_OPENAI,
            )
        ) from exc
    chat_openai = module.__dict__["ChatOpenAI"]

    kwargs: dict[str, object] = {
        "model": model_id,
        "api_key": config.api_key or LLM_STUDIO_API_KEY_PLACEHOLDER,
        "temperature": config.temperature,
        "timeout": config.timeout_seconds,
        "max_retries": config.max_retries,
        "max_tokens": config.max_tokens,
    }
    if config.base_url:
        kwargs["base_url"] = config.base_url
    return chat_openai(**kwargs)


def _openai_compatible_model_id(config: LlmProviderConfig) -> str:
    if config.provider == LLM_PROVIDER_LMSTUDIO and config.model == LLM_MODEL_AUTO:
        try:
            return _lmstudio_model_id(config)
        except LlmProviderError as exc:
            if _is_lmstudio_auto_connection_error(exc):
                return config.model
            raise
    return config.model


def _lmstudio_model_id(config: LlmProviderConfig) -> str:
    models_url = f"{config.base_url.rstrip('/')}/models"
    try:
        response = httpx.get(models_url, timeout=config.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise LlmProviderError(
            context={
                ERROR_CONTEXT_LLM_ERROR_TYPE: type(exc).__name__,
                ERROR_CONTEXT_LLM_PROVIDER: config.provider,
                ERROR_CONTEXT_LLM_BASE_URL: config.base_url,
                ERROR_CONTEXT_LLM_TIMEOUT_SECONDS: config.timeout_seconds,
            }
        ) from exc
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise LlmProviderError(
            context={
                ERROR_CONTEXT_LLM_ERROR_TYPE: LLM_PROVIDER_ERROR_INVALID_MODELS_RESPONSE,
                ERROR_CONTEXT_LLM_PROVIDER: config.provider,
                ERROR_CONTEXT_LLM_BASE_URL: config.base_url,
            }
        )
    for item in data:
        if isinstance(item, dict):
            model_id = str(item.get("id") or "").strip()
            if model_id:
                return model_id
    raise LlmProviderError(
        context={
            ERROR_CONTEXT_LLM_ERROR_TYPE: LLM_PROVIDER_ERROR_NO_LOADED_MODEL,
            ERROR_CONTEXT_LLM_PROVIDER: config.provider,
            ERROR_CONTEXT_LLM_BASE_URL: config.base_url,
        }
    )


def _is_lmstudio_auto_connection_error(exc: LlmProviderError) -> bool:
    error_type = exc.context.get(ERROR_CONTEXT_LLM_ERROR_TYPE)
    return error_type not in {
        LLM_PROVIDER_ERROR_INVALID_MODELS_RESPONSE,
        LLM_PROVIDER_ERROR_NO_LOADED_MODEL,
    }


def _decide_action(
    factory: AgentFactory,
    context: AgentContext,
    request: DecisionRequest,
    *,
    trace_sink: DecisionTraceSink,
) -> Action:
    """一つのSessionで決定し、失敗時だけ決定的fallbackを適用する."""
    started_at = time.perf_counter()
    session = None
    try:
        try:
            session = factory.create(context)
            response = session.decide(request)
            _require_legal_response(request, response)
        except Exception as exc:
            error = (
                exc
                if isinstance(exc, AgentDecisionError)
                else AgentDecisionError(
                    "agent_decision_failed",
                    {"error_type": type(exc).__name__},
                )
            )
            fallback_factory = HeuristicAgentFactory()
            fallback_session = fallback_factory.create(context)
            try:
                response = fallback_session.decide(request)
                _require_legal_response(request, response)
            finally:
                fallback_session.close()
            trace_sink.record_decision(
                DecisionTrace(
                    decision_id=request.decision_id,
                    agent_spec=factory.spec,
                    response=response,
                    latency_ms=_elapsed_milliseconds(started_at),
                    fallback_used=True,
                    error_code=error.code,
                    diagnostics=error.diagnostics,
                )
            )
        else:
            trace_sink.record_decision(
                DecisionTrace(
                    decision_id=request.decision_id,
                    agent_spec=factory.spec,
                    response=response,
                    latency_ms=_elapsed_milliseconds(started_at),
                )
            )
        return _game_action_from_response(context.player_id, response)
    finally:
        if session is not None:
            session.close()


def decide_game_action(
    factory: AgentFactory,
    *,
    context: AgentContext,
    observation: GameView,
    decision_seed: int,
    game_context: AgentGameContext | None = None,
    trace_sink: DecisionTraceSink | None = None,
) -> Action:
    """直接gameを駆動する実験環境向けに標準Agent Sessionを一回実行する."""
    request = _decision_request_from_game(
        context,
        observation,
        game_context=game_context,
        decision_seed=decision_seed,
    )
    return _decide_action(
        factory,
        context,
        request,
        trace_sink=trace_sink or NullDecisionTraceSink(),
    )


def _decision_request_from_game(
    context: AgentContext,
    observation: GameView,
    *,
    game_context: AgentGameContext | None,
    decision_seed: int,
) -> DecisionRequest:
    """Domainの本人用viewを標準Agent SDKの入力へ変換する."""
    players = tuple(
        ObservedPlayer(player.id, player.name, player.status.value == "alive")
        for player in observation.players
    )
    me = next(player for player in players if player.player_id == observation.me.id)
    metadata = agent_metadata_from_game_context(game_context)
    return DecisionRequest(
        decision_id=(
            f"{context.session_id}:{observation.phase.value}:{observation.day}:{decision_seed}"
        ),
        context=context,
        observation=AgentObservation(
            phase=observation.phase.value,
            day=observation.day,
            me=me,
            players=players,
            known_roles=dict(observation.known_roles),
            known_factions=dict(observation.known_factions),
            identity=metadata.identity,
            world=metadata.world,
        ),
        public_timeline=_public_timeline(observation),
        options=tuple(
            DecisionOption(
                action_type=action.type.value,
                ability_id=action.ability_id,
                legal_target_ids=tuple(observation.legal_targets.get(action.key, ())),
                message_max_chars=(
                    LLM_SPEECH_MESSAGE_MAX_CHARS if action.type.value == "speech" else None
                ),
            )
            for action in observation.available_actions
        ),
        decision_seed=decision_seed,
    )


def _public_timeline(observation: GameView) -> tuple[PublicTimelineEvent, ...]:
    items: list[tuple[int, int, str, str | None, dict[str, object]]] = []
    for index, speech in enumerate(observation.history.speeches):
        items.append(
            (
                speech.day,
                index,
                "speech",
                speech.player_id,
                {
                    "message": speech.message,
                    "focus_id": speech.focus_id,
                    "evidence_id": speech.evidence_id,
                },
            )
        )
    speech_count = len(observation.history.speeches)
    for index, vote in enumerate(observation.history.votes):
        items.append(
            (
                vote.day,
                speech_count + index,
                "vote_round",
                None,
                {
                    "votes": dict(vote.votes),
                    "counts": dict(vote.counts),
                    "eliminated_player_id": vote.eliminated_player_id,
                },
            )
        )
    items.sort(key=lambda item: (item[0], item[1]))
    return tuple(
        PublicTimelineEvent(
            sequence=sequence,
            event_type=event_type,
            day=day,
            actor_id=actor_id,
            payload=payload,
        )
        for sequence, (day, _, event_type, actor_id, payload) in enumerate(items, start=1)
    )


def _require_legal_response(request: DecisionRequest, response: DecisionResponse) -> None:
    option = next(
        (
            item
            for item in request.options
            if item.action_type == response.action_type and item.ability_id == response.ability_id
        ),
        None,
    )
    if option is None:
        raise AgentDecisionError("agent_action_not_available")
    if response.target_id is not None and response.target_id not in option.legal_target_ids:
        raise AgentDecisionError("agent_target_not_legal")
    if option.legal_target_ids and response.target_id is None:
        raise AgentDecisionError("agent_target_required")
    if response.action_type == "speech":
        if response.message is None:
            raise AgentDecisionError("agent_message_required")
        if (
            option.message_max_chars is not None
            and len(response.message) > option.message_max_chars
        ):
            raise AgentDecisionError("agent_message_too_long")
    elif response.message is not None:
        raise AgentDecisionError("agent_message_not_allowed")


def _elapsed_milliseconds(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))


def _agent_game_contexts(
    prepared: PreparedAdvanceGame,
    snapshot: Any,
) -> dict[str, AgentGameContext]:
    """Build player-private setup facts without exposing another role or pending action."""
    setup = prepared.config.get("setup_document")
    if not isinstance(setup, dict):
        return {}
    return build_agent_game_contexts(
        setup,
        snapshot,
        setup_checksum=str(prepared.config.get("setup_checksum") or ""),
        mechanics_checksum=str(prepared.config.get("mechanics_checksum") or ""),
        scenario_name=str(prepared.config.get("scenario_name") or ""),
        scenario_premise=str(prepared.config.get("scenario_prompt_premise") or ""),
    )


def _game_action_from_response(player_id: str, response: DecisionResponse) -> Action:
    if response.action_type == "speech":
        if response.message is None:
            raise AgentDecisionError("agent_message_required")
        return Action.speech(
            player_id,
            response.message,
            focus_id=response.focus_id,
            evidence_id=response.evidence_id,
        )

    if response.action_type == "vote":
        if response.target_id is None:
            raise AgentDecisionError("agent_target_required")
        return Action.vote(player_id, response.target_id)

    if response.action_type == "use_ability":
        if response.target_id is None or response.ability_id is None:
            raise AgentDecisionError("agent_ability_payload_required")
        return Action.use_ability(
            player_id,
            response.ability_id,
            response.target_id,
        )

    return Action.pass_(player_id)
