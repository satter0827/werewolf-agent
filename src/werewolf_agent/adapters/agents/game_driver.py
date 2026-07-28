"""Automated-player driver connecting agents and application operations."""

from __future__ import annotations

import logging
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
from werewolf_agent.adapters.agents.messages import (
    MESSAGE_MISSING_ATTACK_TARGET,
    MESSAGE_MISSING_SPEECH_MESSAGE,
    MESSAGE_MISSING_VOTE_TARGET,
    message_langchain_openai_required,
    message_unsupported_llm_provider,
)
from werewolf_agent.adapters.llm.configuration import LlmProviderConfig
from werewolf_agent.adapters.llm.langchain.service import (
    LangChainDecisionProvider,
)
from werewolf_agent.adapters.llm.model_adapters import (
    FakeDecisionModel,
    LangChainChatDecisionModel,
    LlmModelInvocationError,
)
from werewolf_agent.adapters.resources import LlmDefinitions
from werewolf_agent.agents.models import (
    AgentAbilityContext,
    AgentActionType,
    AgentAvailableAction,
    AgentDecision,
    AgentGameContext,
    AgentObservation,
    AgentPhase,
    AgentPlayerStatus,
    AgentScenario,
    DeliberationLevel,
    PlayerProfile,
    VisiblePlayer,
)
from werewolf_agent.agents.ports import PlayerAgent as DecisionProvider
from werewolf_agent.agents.tracing import LlmTraceSink, NullLlmTraceSink
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
    decision_seed: int
    scenario: AgentScenario | None = None
    game_context: AgentGameContext | None = None

    def act(self, observation: GameView) -> Action:
        """Return one structured action for the current observation."""
        agent_observation = _agent_observation_from_game(
            observation,
            profile=self.profile,
            scenario=self.scenario,
            game_context=self.game_context,
            decision_seed=self.decision_seed,
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
    game_contexts: dict[str, AgentGameContext] = field(default_factory=dict)

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
            decision_seed=seed,
            scenario=self.scenario,
            game_context=self.game_contexts.get(player_id),
        )


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
    scenario_name = str(prepared.config.get("scenario_name") or "").strip()
    scenario_premise = str(prepared.config.get("scenario_prompt_premise") or "").strip()
    scenario = (
        AgentScenario(name=scenario_name, premise=scenario_premise)
        if scenario_name and scenario_premise
        else None
    )
    game_contexts = _agent_game_contexts(prepared, snapshot)
    factory = langchain_agent_factory(
        runtime.config,
        definitions=runtime.definitions,
        profiles=_profiles_from_config(prepared.config),
        profile_ids_by_player=profile_ids,
        scenario=scenario,
        game_contexts=game_contexts,
        trace_sink=runtime.trace_sink,
        deliberation_level=DeliberationLevel(str(prepared.config["deliberation_level"])),
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
                "agent_type": "llm",
            },
        )
    return replace(prepared, domain_events=tuple(events))


def langchain_agent_factory(
    config: LlmProviderConfig,
    *,
    definitions: LlmDefinitions,
    profiles: dict[str, PlayerProfile],
    profile_ids_by_player: dict[str, str] | None = None,
    scenario: AgentScenario | None = None,
    game_contexts: dict[str, AgentGameContext] | None = None,
    trace_sink: LlmTraceSink | None = None,
    deliberation_level: DeliberationLevel = DeliberationLevel.STANDARD,
) -> LlmAgentFactory:
    """Return a LangChain-backed agent factory from application settings."""
    return LlmAgentFactory(
        provider=_decision_provider(
            config,
            definitions=definitions,
            trace_sink=trace_sink,
            deliberation_level=deliberation_level,
        ),
        profiles=profiles,
        profile_ids_by_player=profile_ids_by_player or {},
        scenario=scenario,
        game_contexts=game_contexts or {},
    )


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


def _agent_observation_from_game(
    observation: GameView,
    *,
    profile: PlayerProfile | None = None,
    scenario: AgentScenario | None = None,
    game_context: AgentGameContext | None = None,
    decision_seed: int = 0,
) -> AgentObservation:
    return AgentObservation.model_validate(
        {
            "phase": AgentPhase(observation.phase.value),
            "day": observation.day,
            "decision_seed": decision_seed,
            "me": _visible_player_from_game(observation.me),
            "role": observation.me.role if observation.me.role is not None else None,
            "profile": profile,
            "scenario": scenario,
            "game_context": game_context,
            "players": [_visible_player_from_game(player) for player in observation.players],
            "known_roles": dict(observation.known_roles),
            "known_factions": dict(observation.known_factions),
            "available_actions": [
                AgentAvailableAction(
                    type=AgentActionType(action.type.value),
                    ability_id=action.ability_id,
                )
                for action in observation.available_actions
            ],
            "legal_targets": {
                str(action_key): list(player_ids)
                for action_key, player_ids in observation.legal_targets.items()
            },
            "speeches": [
                {
                    "day": speech.day,
                    "player_id": speech.player_id,
                    "message": speech.message,
                    "focus_id": speech.focus_id,
                    "evidence_id": speech.evidence_id,
                }
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


def _agent_game_contexts(
    prepared: PreparedAdvanceGame,
    snapshot: Any,
) -> dict[str, AgentGameContext]:
    """Build player-private setup facts without exposing another role or pending action."""
    setup = prepared.config.get("setup_document")
    if not isinstance(setup, dict):
        return {}
    mechanics = setup.get("mechanics")
    theme = setup.get("theme")
    if not isinstance(mechanics, dict) or not isinstance(theme, dict):
        return {}
    roles = mechanics.get("roles")
    abilities = mechanics.get("abilities")
    rules = mechanics.get("rules")
    if (
        not isinstance(roles, dict)
        or not isinstance(abilities, dict)
        or not isinstance(rules, dict)
    ):
        return {}
    role_names_value = theme.get("role_names")
    role_names = role_names_value if isinstance(role_names_value, dict) else {}
    role_objectives_value = theme.get("role_objectives")
    role_objectives = role_objectives_value if isinstance(role_objectives_value, dict) else {}
    faction_names_value = theme.get("faction_names")
    faction_names = faction_names_value if isinstance(faction_names_value, dict) else {}
    ability_names_value = theme.get("ability_names")
    ability_names = ability_names_value if isinstance(ability_names_value, dict) else {}
    contexts: dict[str, AgentGameContext] = {}
    for player in snapshot.players.values():
        if player.role is None:
            continue
        role = roles.get(player.role)
        if not isinstance(role, dict):
            continue
        ability_contexts: list[AgentAbilityContext] = []
        for ability_id in role.get("abilities") or []:
            ability = abilities.get(str(ability_id))
            if not isinstance(ability, dict):
                continue
            max_uses = ability.get("max_uses")
            used = snapshot.ability_uses.get(player.id, {}).get(str(ability_id), 0)
            if max_uses == "unlimited":
                remaining = None
            elif isinstance(max_uses, int) and not isinstance(max_uses, bool):
                remaining = max(0, max_uses - used)
            else:
                raise ValueError("ability max_uses must be an integer or unlimited")
            ability_contexts.append(
                AgentAbilityContext(
                    id=str(ability_id),
                    name=str(
                        ability_names.get(str(ability_id)) or ability.get("label") or ability_id
                    ),
                    kind=str(ability.get("kind") or ""),
                    remaining_uses=remaining,
                )
            )
        relevant_keys = {
            "day_speech_limit_per_player",
            "allow_self_vote",
            "allow_vote_revision",
            "allow_night_action_revision",
            "vote_tie_resolution",
            "starting_phase",
            "reveal_role_on_death",
            "require_all_actions_before_advance",
        }
        identity_faction = str(role.get("identity_faction") or "")
        victory_team = str(role.get("victory_team") or "")
        contexts[player.id] = AgentGameContext(
            theme_id=str(theme.get("id") or ""),
            theme_name=str(theme.get("name") or ""),
            premise=str(theme.get("premise") or ""),
            role_id=player.role,
            role_name=str(role_names.get(player.role) or role.get("label") or player.role),
            identity_faction=identity_faction,
            identity_faction_name=str(faction_names.get(identity_faction) or identity_faction),
            victory_team=victory_team,
            victory_team_name=str(faction_names.get(victory_team) or victory_team),
            objective=str(role_objectives.get(player.role) or role.get("objective") or ""),
            abilities=tuple(ability_contexts),
            relevant_rules={key: rules[key] for key in sorted(relevant_keys) if key in rules},
            action_names={
                str(key): str(value) for key, value in dict(theme.get("action_names") or {}).items()
            },
            phase_names={
                str(key): str(value) for key, value in dict(theme.get("phase_names") or {}).items()
            },
            setup_checksum=str(prepared.config.get("setup_checksum") or ""),
            mechanics_checksum=str(prepared.config.get("mechanics_checksum") or ""),
        )
    return contexts


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
        return Action.speech(
            decision.player_id,
            decision.message,
            focus_id=decision.focus_id,
            evidence_id=decision.evidence_id,
        )

    if decision.type is AgentActionType.VOTE:
        if decision.target_id is None:
            return Action.pass_(decision.player_id, reason=MESSAGE_MISSING_VOTE_TARGET)
        return Action.vote(decision.player_id, decision.target_id, reason=decision.reason)

    if decision.type is AgentActionType.USE_ABILITY:
        if decision.target_id is None or decision.ability_id is None:
            return Action.pass_(decision.player_id, reason=MESSAGE_MISSING_ATTACK_TARGET)
        return Action.use_ability(
            decision.player_id,
            decision.ability_id,
            decision.target_id,
            reason=decision.reason,
        )

    return Action.pass_(decision.player_id, reason=decision.reason)
