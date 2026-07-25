"""Automated-player driver connecting agents and game use cases."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from importlib import import_module
from typing import Any, Protocol

import httpx

from werewolf_agent.agents.configuration import LlmProviderConfig
from werewolf_agent.agents.langchain.service import (
    LangChainDecisionProvider,
    LlmModelInvocationError,
)
from werewolf_agent.agents.mapping import to_player_profiles
from werewolf_agent.agents.models import (
    AgentActionType,
    AgentDecision,
    AgentObservation,
    AgentPhase,
    AgentPlayerStatus,
    AgentScenario,
    PlayerProfile,
    VisiblePlayer,
)
from werewolf_agent.agents.ports import PlayerAgent as DecisionProvider
from werewolf_agent.agents.tracing import LlmTraceSink, NullLlmTraceSink
from werewolf_agent.configuration.constants import (
    LLM_MODEL_AUTO,
    LLM_PROVIDER_FAKE,
    LLM_PROVIDER_LMSTUDIO,
    LLM_PROVIDER_OPENAI,
    LLM_STUDIO_API_KEY_PLACEHOLDER,
)
from werewolf_agent.configuration.definitions import LlmDefinitions
from werewolf_agent.configuration.messages import (
    MESSAGE_MISSING_ATTACK_TARGET,
    MESSAGE_MISSING_GUARD_TARGET,
    MESSAGE_MISSING_INSPECT_TARGET,
    MESSAGE_MISSING_SPEECH_MESSAGE,
    MESSAGE_MISSING_VOTE_TARGET,
    message_langchain_openai_required,
    message_unsupported_llm_provider,
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
from werewolf_agent.usecase.handlers import (
    commit_prepared_advance,
    prepare_advance_game,
    run_prepared_advance,
)
from werewolf_agent.usecase.models import (
    AdvanceGameCommand,
    AdvanceGameResult,
    PreparedAdvanceGame,
    UsecaseContext,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentRuntime:
    """Dependencies used only while an adapter drives automated players."""

    config: LlmProviderConfig
    definitions: LlmDefinitions
    trace_sink: LlmTraceSink = field(default_factory=NullLlmTraceSink)


class GamePlayerAgent(Protocol):
    """Automated actor used by internal game workflow."""

    def act(self, observation: GameView) -> Action:
        """Return one structured action for the given visible observation."""


class AgentFactory(Protocol):
    """Factory for deterministic player agents."""

    def create(self, player_id: str, *, seed: int) -> GamePlayerAgent:
        """Create one player agent for a deterministic game step."""


@dataclass(frozen=True)
class LlmAgent:
    """Automated player backed by an LLM decision provider."""

    player_id: str
    provider: DecisionProvider
    profile: PlayerProfile
    scenario: AgentScenario | None = None

    def act(self, observation: GameView) -> Action:
        """Return one structured action for the current observation."""
        agent_observation = _agent_observation_from_game(
            observation,
            profile=self.profile,
            scenario=self.scenario,
        )
        try:
            decision = self.provider.choose_decision(self.player_id, agent_observation)
        except LlmModelInvocationError as exc:
            raise LlmProviderError(context=exc.context) from exc
        return _game_action_from_decision(decision)


@dataclass(frozen=True)
class LlmAgentFactory:
    """Create LLM agents for automated games."""

    provider: DecisionProvider
    profiles: dict[str, PlayerProfile]
    profile_ids_by_player: dict[str, str]
    scenario: AgentScenario | None = None

    def create(self, player_id: str, *, seed: int) -> LlmAgent:
        """Create one LLM agent for a deterministic game step."""
        profile_id = self.profile_ids_by_player.get(player_id)
        if profile_id is None or profile_id not in self.profiles:
            profile_ids = sorted(self.profiles)
            profile_id = profile_ids[seed % len(profile_ids)]
        profile = self.profiles[profile_id]
        return LlmAgent(
            player_id=player_id,
            provider=self.provider,
            profile=profile,
            scenario=self.scenario,
        )


def advance_game(
    context: UsecaseContext,
    command: AdvanceGameCommand,
    *,
    runtime: AgentRuntime,
) -> AdvanceGameResult:
    """Drive automated players, advance the domain, and commit the result."""
    prepared = prepare_advance_game(command, dependencies=context)
    driven = drive_prepared_game(prepared, context=context, runtime=runtime)
    computed = run_prepared_advance(driven, dependencies=context)
    return commit_prepared_advance(computed, dependencies=context)


def drive_prepared_game(
    prepared: PreparedAdvanceGame,
    *,
    context: UsecaseContext,
    runtime: AgentRuntime,
) -> PreparedAdvanceGame:
    """Generate automated actions without placing agent logic in usecase."""
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
    strategy_id = str(
        prepared.config.get("agent_strategy_id") or runtime.config.default_agent_strategy_id
    )
    scenario_name = str(prepared.config.get("scenario_name") or "").strip()
    scenario_premise = str(prepared.config.get("scenario_prompt_premise") or "").strip()
    scenario = (
        AgentScenario(name=scenario_name, premise=scenario_premise)
        if scenario_name and scenario_premise
        else None
    )
    factory = langchain_agent_factory(
        runtime.config,
        definitions=runtime.definitions,
        agent_strategy_id=strategy_id,
        profile_ids_by_player=profile_ids,
        scenario=scenario,
        trace_sink=runtime.trace_sink,
    )
    events = []
    for index, player in enumerate(snapshot.players.values()):
        if player.status.value != "alive" or player.id in manual_player_ids:
            continue
        observation = game.view_for(player.id)
        if not observation.available_actions:
            continue
        agent = factory.create(
            player.id,
            seed=(prepared.seed or 0) + prepared.version * 1009 + index * 131,
        )
        action = agent.act(observation)
        events.extend(game.submit(action))
        snapshot = game.snapshot()
        logger.debug(
            "game.agent_action.generated",
            extra={
                "event_action": "game.agent_action.generated",
                "game_phase": snapshot.phase.value,
                "game_day": snapshot.day,
                "game_version": prepared.version,
                "agent_type": context.config.supported_agent_type,
            },
        )
    return replace(prepared, domain_events=tuple(events))


def langchain_agent_factory(
    config: LlmProviderConfig,
    *,
    definitions: LlmDefinitions,
    agent_strategy_id: str,
    profile_ids_by_player: dict[str, str] | None = None,
    scenario: AgentScenario | None = None,
    trace_sink: LlmTraceSink | None = None,
) -> LlmAgentFactory:
    """Return a LangChain-backed agent factory from use case settings."""
    profiles = to_player_profiles(definitions.players)
    return LlmAgentFactory(
        provider=_decision_provider(
            config,
            definitions=definitions,
            agent_strategy_id=agent_strategy_id,
            trace_sink=trace_sink,
        ),
        profiles=profiles.profiles,
        profile_ids_by_player=profile_ids_by_player or {},
        scenario=scenario,
    )


def _decision_provider(
    config: LlmProviderConfig,
    *,
    definitions: LlmDefinitions,
    agent_strategy_id: str,
    trace_sink: LlmTraceSink | None,
) -> LangChainDecisionProvider:
    agent_strategy = definitions.agent_strategies.strategy_for(agent_strategy_id)
    if config.provider == LLM_PROVIDER_FAKE:
        return LangChainDecisionProvider(
            prompt=definitions.prompt,
            fake_responses=definitions.fake_responses,
            agent_strategy=agent_strategy,
            provider_name=config.provider,
            model_name=config.model,
            trace_sink=trace_sink,
            structured_output_mode=config.structured_output_mode,
            validation_retry_count=config.validation_retry_count,
            graph_max_steps=config.graph_max_steps,
            fallback_policy=config.fallback_policy,
        )
    if config.provider in {LLM_PROVIDER_LMSTUDIO, LLM_PROVIDER_OPENAI}:
        model_id = _openai_compatible_model_id(config)
        return LangChainDecisionProvider(
            prompt=definitions.prompt,
            model=_openai_compatible_model(config, model_id=model_id),
            agent_strategy=agent_strategy,
            provider_name=config.provider,
            model_name=model_id,
            base_url=config.base_url,
            timeout_seconds=config.timeout_seconds,
            max_tokens=config.max_tokens,
            trace_sink=trace_sink,
            structured_output_mode=config.structured_output_mode,
            validation_retry_count=config.validation_retry_count,
            graph_max_steps=config.graph_max_steps,
            fallback_policy=config.fallback_policy,
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


def _agent_observation_from_game(
    observation: GameView,
    *,
    profile: PlayerProfile | None = None,
    scenario: AgentScenario | None = None,
) -> AgentObservation:
    return AgentObservation.model_validate(
        {
            "phase": AgentPhase(observation.phase.value),
            "day": observation.day,
            "me": _visible_player_from_game(observation.me),
            "role": observation.me.role if observation.me.role is not None else None,
            "profile": profile,
            "scenario": scenario,
            "players": [_visible_player_from_game(player) for player in observation.players],
            "known_roles": dict(observation.known_roles),
            "available_actions": [
                AgentActionType(action_type.value) for action_type in observation.available_actions
            ],
            "legal_targets": {
                AgentActionType(action_type.value): list(player_ids)
                for action_type, player_ids in observation.legal_targets.items()
            },
            "speeches": [
                {"player_id": speech.player_id, "message": speech.message}
                for speech in observation.history.speeches
                if speech.message
            ],
            "vote_rounds": [
                {
                    "day": vote.day,
                    "votes": dict(vote.votes),
                    "counts": dict(vote.counts),
                    "eliminated_player_id": vote.eliminated_player_id,
                }
                for vote in observation.history.votes
            ],
        }
    )


def _visible_player_from_game(player: Any) -> VisiblePlayer:
    return VisiblePlayer(
        id=player.id,
        name=player.name,
        status=AgentPlayerStatus(player.status.value),
    )


def _game_action_from_decision(decision: AgentDecision) -> Action:
    if decision.type is AgentActionType.SPEECH:
        if decision.message is None:
            return Action.pass_(decision.player_id, reason=MESSAGE_MISSING_SPEECH_MESSAGE)
        return Action.speech(decision.player_id, decision.message)

    if decision.type is AgentActionType.VOTE:
        if decision.target_id is None:
            return Action.pass_(decision.player_id, reason=MESSAGE_MISSING_VOTE_TARGET)
        return Action.vote(decision.player_id, decision.target_id, reason=decision.reason)

    if decision.type is AgentActionType.WEREWOLF_ATTACK:
        if decision.target_id is None:
            return Action.pass_(decision.player_id, reason=MESSAGE_MISSING_ATTACK_TARGET)
        return Action.attack(decision.player_id, decision.target_id, reason=decision.reason)

    if decision.type is AgentActionType.SEER_INSPECT:
        if decision.target_id is None:
            return Action.pass_(decision.player_id, reason=MESSAGE_MISSING_INSPECT_TARGET)
        return Action.inspect(decision.player_id, decision.target_id, reason=decision.reason)

    if decision.type is AgentActionType.KNIGHT_GUARD:
        if decision.target_id is None:
            return Action.pass_(decision.player_id, reason=MESSAGE_MISSING_GUARD_TARGET)
        return Action.guard(decision.player_id, decision.target_id, reason=decision.reason)

    return Action.pass_(decision.player_id, reason=decision.reason)
