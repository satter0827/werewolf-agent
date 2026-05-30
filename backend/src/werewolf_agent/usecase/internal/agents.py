"""Internal agent adapters used by game jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from werewolf_agent.commons.shared.messages import (
    MESSAGE_MISSING_ATTACK_TARGET,
    MESSAGE_MISSING_GUARD_TARGET,
    MESSAGE_MISSING_INSPECT_TARGET,
    MESSAGE_MISSING_SPEECH_MESSAGE,
    MESSAGE_MISSING_VOTE_TARGET,
)
from werewolf_agent.domain.game.models import Action, Observation, Player
from werewolf_agent.domain.llm.models import (
    AgentActionType,
    AgentDecision,
    AgentObservation,
    AgentPhase,
    AgentPlayerStatus,
    AgentRole,
    VisiblePlayer,
)
from werewolf_agent.domain.llm.ports import LlmDecisionProvider
from werewolf_agent.domain.llm.service import build_fake_decision_provider
from werewolf_agent.usecase.jobs.games import LlmProviderConfig


class PlayerAgent(Protocol):
    """Automated actor used by internal game workflow."""

    def act(self, observation: Observation) -> Action:
        """Return one structured action for the given visible observation."""


class AgentFactory(Protocol):
    """Factory for deterministic player agents."""

    def create(self, player_id: str, *, seed: int) -> PlayerAgent:
        """Create one player agent for a deterministic run step."""


@dataclass(frozen=True)
class LlmAgent:
    """Automated player backed by an LLM decision provider."""

    player_id: str
    provider: LlmDecisionProvider

    def act(self, observation: Observation) -> Action:
        """Return one structured action for the current observation."""
        agent_observation = _agent_observation_from_game(observation)
        decision = self.provider.choose_decision(self.player_id, agent_observation)
        return _game_action_from_decision(decision)


@dataclass(frozen=True)
class LlmAgentFactory:
    """Create LLM agents for automated game runs."""

    provider: LlmDecisionProvider

    def create(self, player_id: str, *, seed: int) -> LlmAgent:
        """Create one LLM agent for a deterministic run step."""
        _ = seed
        return LlmAgent(player_id=player_id, provider=self.provider)


def langchain_agent_factory(config: LlmProviderConfig) -> LlmAgentFactory:
    """Return a LangChain-backed agent factory from use case settings."""
    if config.provider != "fake":
        raise ValueError(f"Unsupported LLM provider: {config.provider}.")
    return LlmAgentFactory(
        provider=build_fake_decision_provider(
            prompt_path=config.prompt_file,
            fake_responses_path=config.fake_responses_file,
        )
    )


def _agent_observation_from_game(observation: Observation) -> AgentObservation:
    return AgentObservation.model_validate(
        {
            "phase": AgentPhase(observation.phase.value),
            "day": observation.day,
            "me": _visible_player_from_game(observation.me),
            "role": AgentRole(observation.me.role.value)
            if observation.me.role is not None
            else None,
            "players": [_visible_player_from_game(player) for player in observation.players],
            "known_roles": {
                player_id: AgentRole(role.value)
                for player_id, role in observation.known_roles.items()
            },
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
