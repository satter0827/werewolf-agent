"""Internal agent adapters used by game jobs."""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field

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
    FakeLlmConfig,
    VisiblePlayer,
)
from werewolf_agent.domain.llm.service import choose_decision

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FakeLlmAgent:
    """Automated player backed by an LLM decision provider."""

    player_id: str
    config: FakeLlmConfig
    rng: random.Random

    def act(self, observation: Observation) -> Action:
        """Return one structured action for the current observation."""
        agent_observation = _agent_observation_from_game(observation)
        decision = choose_decision(
            self.player_id,
            agent_observation,
            config=self.config,
            rng=self.rng,
        )
        logger.debug(
            "fake_llm decision selected",
            extra={
                "actor_id": self.player_id,
                "candidate_count": _safe_candidate_count(agent_observation),
                "day": agent_observation.day,
                "decision_type": decision.type.value,
                "phase": agent_observation.phase.value,
            },
        )
        return _game_action_from_decision(decision)


@dataclass(frozen=True)
class FakeLlmAgentFactory:
    """Create FakeLLM agents for automated game runs."""

    config: FakeLlmConfig = field(default_factory=FakeLlmConfig)

    def create(self, player_id: str, *, seed: int) -> FakeLlmAgent:
        """Create one FakeLLM agent using the configured seed policy."""
        seed_offset = int(self.config.randomness * 10000)
        rng = (
            random.Random(seed + seed_offset)
            if self.config.strategy == "seeded"
            else random.Random()
        )
        return FakeLlmAgent(player_id=player_id, config=self.config, rng=rng)


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


def _safe_candidate_count(observation: AgentObservation) -> int:
    return sum(
        1
        for player in observation.players
        if player.status is AgentPlayerStatus.ALIVE and player.id != observation.me.id
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
