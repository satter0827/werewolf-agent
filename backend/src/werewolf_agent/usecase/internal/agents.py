"""Internal agent adapters used by game jobs."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Protocol

import httpx

from werewolf_agent.commons.shared.constants import (
    LLM_MODEL_AUTO,
    LLM_PROVIDER_FAKE,
    LLM_PROVIDER_LMSTUDIO,
    LLM_PROVIDER_OPENAI,
    LLM_STUDIO_API_KEY_PLACEHOLDER,
)
from werewolf_agent.commons.shared.definitions import LlmDefinitions
from werewolf_agent.commons.shared.llm_tracing import LlmTraceSink
from werewolf_agent.commons.shared.messages import (
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
from werewolf_agent.domain.game.models import Action, Observation, Player
from werewolf_agent.domain.llm.models import (
    AgentActionType,
    AgentDecision,
    AgentObservation,
    AgentPhase,
    AgentPlayerStatus,
    AgentScenario,
    PlayerProfile,
    VisiblePlayer,
)
from werewolf_agent.domain.llm.ports import LlmDecisionProvider
from werewolf_agent.domain.llm.service import LangChainDecisionProvider, LlmModelInvocationError
from werewolf_agent.usecase.internal.definitions import to_player_profiles
from werewolf_agent.usecase.jobs.games import LlmProviderConfig


class PlayerAgent(Protocol):
    """Automated actor used by internal game workflow."""

    def act(self, observation: Observation) -> Action:
        """Return one structured action for the given visible observation."""


class AgentFactory(Protocol):
    """Factory for deterministic player agents."""

    def create(self, player_id: str, *, seed: int) -> PlayerAgent:
        """Create one player agent for a deterministic game step."""


@dataclass(frozen=True)
class LlmAgent:
    """Automated player backed by an LLM decision provider."""

    player_id: str
    provider: LlmDecisionProvider
    profile: PlayerProfile
    scenario: AgentScenario | None = None

    def act(self, observation: Observation) -> Action:
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

    provider: LlmDecisionProvider
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
    observation: Observation,
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


def _visible_player_from_game(player: Player) -> VisiblePlayer:
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
