"""Provider-independent decision services for automated players."""

from __future__ import annotations

import random
from collections.abc import Sequence

from werewolf_agent.commons.shared.messages import (
    MESSAGE_DUMMY_SEEDED_ATTACK,
    MESSAGE_DUMMY_SEEDED_GUARD,
    MESSAGE_DUMMY_SEEDED_INSPECTION,
    MESSAGE_DUMMY_SEEDED_VOTE,
    MESSAGE_NO_ATTACK_TARGETS,
    MESSAGE_NO_GUARD_TARGETS,
    MESSAGE_NO_INSPECT_TARGETS,
    MESSAGE_NO_VALID_VOTE_TARGETS,
    MESSAGE_OBSERVATION_BELONGS_TO_ANOTHER_PLAYER,
    MESSAGE_PLAYER_IS_DEAD,
    MESSAGE_ROLE_HAS_NO_NIGHT_ACTION,
    message_no_action_for_phase,
)
from werewolf_agent.domain.llm.models import (
    AgentDecision,
    AgentObservation,
    AgentPhase,
    AgentPlayerStatus,
    AgentRole,
)

_DEFAULT_SPEECH_TEMPLATES: tuple[str, ...] = (
    "I want to hear more from {target_name}.",
    "{target_name}'s vote history looks worth checking.",
    "I will compare today's claims before voting.",
)


def choose_dummy_decision(
    player_id: str,
    observation: AgentObservation,
    *,
    rng: random.Random,
    speech_templates: Sequence[str] = _DEFAULT_SPEECH_TEMPLATES,
) -> AgentDecision:
    """Return one deterministic dummy decision from visible player context."""
    if observation.me.id != player_id:
        return AgentDecision.pass_(
            player_id=player_id,
            reason=MESSAGE_OBSERVATION_BELONGS_TO_ANOTHER_PLAYER,
        )
    if observation.me.status is not AgentPlayerStatus.ALIVE:
        return AgentDecision.pass_(player_id=player_id, reason=MESSAGE_PLAYER_IS_DEAD)
    if observation.phase is AgentPhase.DAY_DISCUSSION:
        return _dummy_speech_decision(player_id, observation, rng, speech_templates)
    if observation.phase is AgentPhase.VOTING:
        return _dummy_vote_decision(player_id, observation, rng)
    if observation.phase is AgentPhase.NIGHT:
        return _dummy_night_decision(player_id, observation, rng)
    return AgentDecision.pass_(
        player_id=player_id,
        reason=message_no_action_for_phase(observation.phase.value),
    )


def _dummy_speech_decision(
    player_id: str,
    observation: AgentObservation,
    rng: random.Random,
    speech_templates: Sequence[str],
) -> AgentDecision:
    candidates = _alive_candidate_ids(observation, include_self=False)
    target_id = _choose(candidates, rng)
    target_name = _name_for(observation, target_id) if target_id is not None else "everyone"
    template = rng.choice(tuple(speech_templates))
    return AgentDecision.speech(
        player_id=player_id,
        message=template.format(target_name=target_name),
    )


def _dummy_vote_decision(
    player_id: str,
    observation: AgentObservation,
    rng: random.Random,
) -> AgentDecision:
    candidates = _alive_candidate_ids(observation, include_self=False)
    target_id = _choose(candidates, rng)
    if target_id is None:
        return AgentDecision.pass_(player_id=player_id, reason=MESSAGE_NO_VALID_VOTE_TARGETS)
    return AgentDecision.vote(
        player_id=player_id,
        target_id=target_id,
        reason=MESSAGE_DUMMY_SEEDED_VOTE,
    )


def _dummy_night_decision(
    player_id: str,
    observation: AgentObservation,
    rng: random.Random,
) -> AgentDecision:
    if observation.role is AgentRole.WEREWOLF:
        return _dummy_werewolf_attack(player_id, observation, rng)
    if observation.role is AgentRole.SEER:
        return _dummy_seer_inspect(player_id, observation, rng)
    if observation.role is AgentRole.KNIGHT:
        return _dummy_knight_guard(player_id, observation, rng)
    return AgentDecision.pass_(player_id=player_id, reason=MESSAGE_ROLE_HAS_NO_NIGHT_ACTION)


def _dummy_werewolf_attack(
    player_id: str,
    observation: AgentObservation,
    rng: random.Random,
) -> AgentDecision:
    candidates = [
        candidate_id
        for candidate_id in _alive_candidate_ids(observation, include_self=False)
        if observation.known_roles.get(candidate_id) is not AgentRole.WEREWOLF
    ]
    target_id = _choose(candidates, rng)
    if target_id is None:
        return AgentDecision.pass_(player_id=player_id, reason=MESSAGE_NO_ATTACK_TARGETS)
    return AgentDecision.attack(
        player_id=player_id,
        target_id=target_id,
        reason=MESSAGE_DUMMY_SEEDED_ATTACK,
    )


def _dummy_seer_inspect(
    player_id: str,
    observation: AgentObservation,
    rng: random.Random,
) -> AgentDecision:
    unknown_candidates = [
        candidate_id
        for candidate_id in _alive_candidate_ids(observation, include_self=False)
        if candidate_id not in observation.known_roles
    ]
    fallback_candidates = _alive_candidate_ids(observation, include_self=False)
    target_id = _choose(unknown_candidates or fallback_candidates, rng)
    if target_id is None:
        return AgentDecision.pass_(player_id=player_id, reason=MESSAGE_NO_INSPECT_TARGETS)
    return AgentDecision.inspect(
        player_id=player_id,
        target_id=target_id,
        reason=MESSAGE_DUMMY_SEEDED_INSPECTION,
    )


def _dummy_knight_guard(
    player_id: str,
    observation: AgentObservation,
    rng: random.Random,
) -> AgentDecision:
    candidates = _alive_candidate_ids(observation, include_self=True)
    target_id = _choose(candidates, rng)
    if target_id is None:
        return AgentDecision.pass_(player_id=player_id, reason=MESSAGE_NO_GUARD_TARGETS)
    return AgentDecision.guard(
        player_id=player_id,
        target_id=target_id,
        reason=MESSAGE_DUMMY_SEEDED_GUARD,
    )


def _alive_candidate_ids(observation: AgentObservation, *, include_self: bool) -> list[str]:
    return [
        player.id
        for player in observation.players
        if player.status is AgentPlayerStatus.ALIVE
        and (include_self or player.id != observation.me.id)
    ]


def _choose(candidates: Sequence[str], rng: random.Random) -> str | None:
    if not candidates:
        return None
    return rng.choice(sorted(candidates))


def _name_for(observation: AgentObservation, player_id: str | None) -> str:
    if player_id is None:
        return "everyone"
    for player in observation.players:
        if player.id == player_id:
            return player.name
    return player_id


__all__ = ["choose_dummy_decision"]
