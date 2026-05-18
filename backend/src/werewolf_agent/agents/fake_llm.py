"""Deterministic fake LLM agent for local game orchestration tests."""

from __future__ import annotations

import random
from collections.abc import Sequence

from werewolf_agent.domain.models import (
    AgentAction,
    KnightGuardAction,
    Observation,
    PassAction,
    Phase,
    PlayerStatus,
    Role,
    SeerInspectAction,
    SpeechAction,
    VoteAction,
    WerewolfAttackAction,
)

DEFAULT_SPEECH_TEMPLATES: tuple[str, ...] = (
    "I want to hear more from {target_name}.",
    "{target_name}'s vote history looks worth checking.",
    "I will compare today's claims before voting.",
)


class FakeLlmAgent:
    """Seeded agent that mimics structured LLM decisions without a provider call."""

    def __init__(
        self,
        player_id: str,
        *,
        rng: random.Random | None = None,
        speech_templates: Sequence[str] = DEFAULT_SPEECH_TEMPLATES,
    ) -> None:
        self.player_id = player_id
        self._rng = rng or random.Random()
        self._speech_templates = tuple(speech_templates) or DEFAULT_SPEECH_TEMPLATES

    def act(self, observation: Observation) -> AgentAction:
        """Return one structured action for the current observation."""
        if observation.player_id != self.player_id:
            return PassAction(
                player_id=self.player_id,
                reason="observation belongs to another player",
            )
        if observation.self_player.status is not PlayerStatus.ALIVE:
            return PassAction(player_id=self.player_id, reason="player is dead")
        if observation.phase is Phase.DAY_DISCUSSION:
            return self._speak(observation)
        if observation.phase is Phase.VOTING:
            return self._vote(observation)
        if observation.phase is Phase.NIGHT:
            return self._night_action(observation)
        return PassAction(
            player_id=self.player_id,
            reason=f"no action for {observation.phase.value}",
        )

    def _speak(self, observation: Observation) -> SpeechAction:
        candidates = _alive_candidate_ids(observation, include_self=False)
        target_id = _choose(candidates, self._rng)
        target_name = _name_for(observation, target_id) if target_id is not None else "everyone"
        template = self._rng.choice(self._speech_templates)
        return SpeechAction(
            player_id=self.player_id,
            message=template.format(target_name=target_name),
        )

    def _vote(self, observation: Observation) -> AgentAction:
        candidates = _alive_candidate_ids(observation, include_self=False)
        target_id = _choose(candidates, self._rng)
        if target_id is None:
            return PassAction(player_id=self.player_id, reason="no valid vote targets")
        return VoteAction(
            player_id=self.player_id,
            target_id=target_id,
            reason="fake-llm seeded vote",
        )

    def _night_action(self, observation: Observation) -> AgentAction:
        role = observation.self_player.role
        if role is Role.WEREWOLF:
            return self._werewolf_attack(observation)
        if role is Role.SEER:
            return self._seer_inspect(observation)
        if role is Role.KNIGHT:
            return self._knight_guard(observation)
        return PassAction(player_id=self.player_id, reason="role has no night action")

    def _werewolf_attack(self, observation: Observation) -> AgentAction:
        candidates = [
            player_id
            for player_id in _alive_candidate_ids(observation, include_self=False)
            if observation.known_roles.get(player_id) is not Role.WEREWOLF
        ]
        target_id = _choose(candidates, self._rng)
        if target_id is None:
            return PassAction(player_id=self.player_id, reason="no attack targets")
        return WerewolfAttackAction(
            player_id=self.player_id,
            target_id=target_id,
            reason="fake-llm seeded attack",
        )

    def _seer_inspect(self, observation: Observation) -> AgentAction:
        unknown_candidates = [
            player_id
            for player_id in _alive_candidate_ids(observation, include_self=False)
            if player_id not in observation.known_roles
        ]
        fallback_candidates = _alive_candidate_ids(observation, include_self=False)
        target_id = _choose(unknown_candidates or fallback_candidates, self._rng)
        if target_id is None:
            return PassAction(player_id=self.player_id, reason="no inspect targets")
        return SeerInspectAction(
            player_id=self.player_id,
            target_id=target_id,
            reason="fake-llm seeded inspection",
        )

    def _knight_guard(self, observation: Observation) -> AgentAction:
        candidates = _alive_candidate_ids(observation, include_self=True)
        target_id = _choose(candidates, self._rng)
        if target_id is None:
            return PassAction(player_id=self.player_id, reason="no guard targets")
        return KnightGuardAction(
            player_id=self.player_id,
            target_id=target_id,
            reason="fake-llm seeded guard",
        )


def _alive_candidate_ids(observation: Observation, *, include_self: bool) -> list[str]:
    return [
        player.player_id
        for player in observation.players
        if player.status is PlayerStatus.ALIVE
        and (include_self or player.player_id != observation.player_id)
    ]


def _choose(candidates: Sequence[str], rng: random.Random) -> str | None:
    if not candidates:
        return None
    return rng.choice(sorted(candidates))


def _name_for(observation: Observation, player_id: str | None) -> str:
    if player_id is None:
        return "everyone"
    for player in observation.players:
        if player.player_id == player_id:
            return player.name
    return player_id
