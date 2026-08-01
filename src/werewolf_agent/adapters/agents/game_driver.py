"""Automated-player driver connecting agents and application operations."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from importlib import import_module
from typing import Any

import httpx

from werewolf_agent.adapters.agents.constants import (
    LLM_MODEL_AUTO,
    LLM_PROVIDER_FAKE,
    LLM_PROVIDER_LMSTUDIO,
    LLM_PROVIDER_OPENAI,
    LLM_STUDIO_API_KEY_PLACEHOLDER,
)
from werewolf_agent.adapters.agents.game_context import (
    SetupAgentMetadataProvider,
)
from werewolf_agent.adapters.agents.messages import (
    message_langchain_openai_required,
    message_unsupported_llm_provider,
)
from werewolf_agent.adapters.llm.agent import LangChainAgentFactory
from werewolf_agent.adapters.llm.configuration import LlmProviderConfig
from werewolf_agent.adapters.llm.langchain.service import (
    LangChainDecisionProvider,
)
from werewolf_agent.adapters.llm.model_adapters import (
    FakeDecisionModel,
    LangChainChatDecisionModel,
)
from werewolf_agent.adapters.llm.models import DeliberationLevel, PlayerProfile
from werewolf_agent.adapters.llm.tracing import LlmTraceSink, NullLlmTraceSink
from werewolf_agent.adapters.resources import LlmDefinitions
from werewolf_agent.agents import AgentFactory
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
from werewolf_agent.domain import GameEvent, GameState, Phase, PlayerStatus
from werewolf_agent.simulation import (
    DecisionTraceSink,
    NullDecisionTraceSink,
    PlayerController,
    SimulationLimits,
    SimulationRunner,
    SimulationSpec,
    SimulationStepKind,
    SimulationStopReason,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentRuntime:
    """Dependencies used only while an adapter drives automated players."""

    config: LlmProviderConfig
    definitions: LlmDefinitions
    trace_sink: LlmTraceSink = field(default_factory=NullLlmTraceSink)
    agent_factories: Mapping[str, AgentFactory] = field(default_factory=dict)
    decision_trace_sink: DecisionTraceSink = field(default_factory=lambda: NullDecisionTraceSink())


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
    metadata_provider = _metadata_provider(prepared)
    profiles: dict[str, PlayerProfile] | None = None
    provider: LangChainDecisionProvider | None = None
    controllers: dict[str, PlayerController] = {}
    for index, player in enumerate(snapshot.players.values()):
        observation = game.view_for(player.id)
        if player.id in manual_player_ids or not observation.available_actions:
            controllers[player.id] = PlayerController(player.id)
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
        controllers[player.id] = PlayerController(
            player.id,
            factory,
            metadata_provider=metadata_provider,
        )
    session = SimulationRunner().start(
        game,
        SimulationSpec(
            simulation_id=f"worker:{prepared.game_id}:{prepared.version}",
            game_id=prepared.game_id,
            seed=prepared.seed or 0,
            controllers=controllers,
            limits=SimulationLimits(
                max_actions=_phase_action_limit(snapshot),
                max_phases=1,
            ),
            phase_seed=prepared.phase_seed,
        ),
        trace_sink=runtime.decision_trace_sink,
    )
    events: list[GameEvent] = []
    try:
        while True:
            step = session.step()
            events.extend(step.events)
            if step.kind is SimulationStepKind.AGENT_ACTION:
                current = game.snapshot()
                logger.debug(
                    "game.agent_action.generated",
                    extra={
                        "event_action": "game.agent_action.generated",
                        "game_phase": current.phase.value,
                        "game_day": current.day,
                        "game_version": prepared.version,
                        "agent_type": "llm",
                    },
                )
            if step.kind is SimulationStepKind.PHASE_ADVANCED:
                break
            if step.stop_reason is not None:
                if step.stop_reason is SimulationStopReason.WAITING_FOR_MANUAL:
                    raise RuntimeError("prepared advance unexpectedly requires manual input")
                raise RuntimeError(f"prepared advance stopped: {step.stop_reason}")
    finally:
        session.close()
    return replace(
        prepared,
        domain_events=tuple(events),
        domain_transition_complete=True,
    )


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


def _metadata_provider(prepared: PreparedAdvanceGame) -> SetupAgentMetadataProvider | None:
    """準備済みsetupがある場合だけ動的な本人用metadata providerを返す."""
    setup = prepared.config.get("setup_document")
    if not isinstance(setup, dict):
        return None
    return SetupAgentMetadataProvider(
        setup=setup,
        snapshot=prepared.game.snapshot,
        setup_checksum=str(prepared.config.get("setup_checksum") or ""),
        mechanics_checksum=str(prepared.config.get("mechanics_checksum") or ""),
        scenario_name=str(prepared.config.get("scenario_name") or ""),
        scenario_premise=str(prepared.config.get("scenario_prompt_premise") or ""),
    )


def _phase_action_limit(snapshot: GameState) -> int:
    """現在phaseでdomain設定上適用可能な最大action数を返す."""
    alive_ids = {
        player.id for player in snapshot.players.values() if player.status is PlayerStatus.ALIVE
    }
    if snapshot.phase is not Phase.DAY_DISCUSSION:
        return max(len(alive_ids), 1)
    round_ = snapshot.pending_actions.discussion_round
    if round_ is None:
        return 1
    remaining_cycles = snapshot.config.discussion.cycles_per_day - round_.cycle
    current_remaining = len(round_.actor_order) - round_.cursor
    if round_.submission_mode.value == "sealed":
        current_remaining -= len(snapshot.pending_actions.discussion_actions)
    future_actions = remaining_cycles * len(alive_ids) * 2
    if round_.kind.value == "opening":
        future_actions += len(alive_ids)
    return max(current_remaining + future_actions, 1)
