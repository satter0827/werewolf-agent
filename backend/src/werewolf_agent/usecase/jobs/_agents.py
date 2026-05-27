"""Private agent adapters used by game jobs."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

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
from werewolf_agent.domain.llm.service import choose_dummy_decision


class _DummyAgent:
    """Seeded dummy agent that returns structured actions without a provider call."""

    def __init__(
        self,
        player_id: str,
        *,
        rng: random.Random | None = None,
        speech_templates: Sequence[str] | None = None,
    ) -> None:
        self.player_id = player_id
        self._rng = rng or random.Random()
        self._speech_templates = tuple(speech_templates) if speech_templates is not None else None

    def act(self, observation: Observation) -> Action:
        """Return one structured action for the current observation."""
        agent_observation = _agent_observation_from_game(observation)
        if self._speech_templates:
            decision = choose_dummy_decision(
                self.player_id,
                agent_observation,
                rng=self._rng,
                speech_templates=self._speech_templates,
            )
            return _game_action_from_decision(decision)
        decision = choose_dummy_decision(self.player_id, agent_observation, rng=self._rng)
        return _game_action_from_decision(decision)


@dataclass(frozen=True)
class _DummyAgentFactory:
    """Create deterministic dummy agents for automated MVP game runs."""

    def create(self, player_id: str, *, seed: int) -> _DummyAgent:
        """Create one dummy agent with an injected deterministic seed."""
        return _DummyAgent(player_id, rng=random.Random(seed))


def _agent_observation_from_game(observation: Observation) -> AgentObservation:
    return AgentObservation(
        phase=AgentPhase(observation.phase.value),
        day=observation.day,
        me=_visible_player_from_game(observation.me),
        role=AgentRole(observation.me.role.value) if observation.me.role is not None else None,
        players=[_visible_player_from_game(player) for player in observation.players],
        known_roles={
            player_id: AgentRole(role.value) for player_id, role in observation.known_roles.items()
        },
        available_actions=[
            AgentActionType(action_type.value) for action_type in observation.available_actions
        ],
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
