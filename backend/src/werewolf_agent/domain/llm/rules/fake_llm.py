"""FakeLLM decision rules for visible, provider-independent context."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Mapping, Sequence

from werewolf_agent.commons.shared.messages import (
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
    AgentActionType,
    AgentDecision,
    AgentObservation,
    AgentPhase,
    AgentPlayerStatus,
    AgentRole,
    FakeLlmConfig,
)


def choose_fake_llm_decision(
    player_id: str,
    observation: AgentObservation,
    *,
    config: FakeLlmConfig,
    rng: random.Random,
) -> AgentDecision:
    """Return one FakeLLM decision from visible player context."""
    if observation.me.id != player_id:
        return AgentDecision.pass_(
            player_id=player_id,
            reason=MESSAGE_OBSERVATION_BELONGS_TO_ANOTHER_PLAYER,
        )
    if observation.me.status is not AgentPlayerStatus.ALIVE:
        return AgentDecision.pass_(player_id=player_id, reason=MESSAGE_PLAYER_IS_DEAD)
    if observation.phase is AgentPhase.DAY_DISCUSSION:
        return _speech_decision(player_id, observation, config, rng)
    if observation.phase is AgentPhase.VOTING:
        return _vote_decision(player_id, observation, config, rng)
    if observation.phase is AgentPhase.NIGHT:
        return _night_decision(player_id, observation, config, rng)
    return AgentDecision.pass_(
        player_id=player_id,
        reason=message_no_action_for_phase(observation.phase.value),
    )


def _speech_decision(
    player_id: str,
    observation: AgentObservation,
    config: FakeLlmConfig,
    rng: random.Random,
) -> AgentDecision:
    scores = _candidate_scores(observation, include_self=False)
    target_id = _weighted_choice(scores, rng, randomness=config.randomness)
    context = _decision_context(
        observation,
        config,
        rng,
        action=AgentActionType.SPEECH,
        target_id=target_id,
    )
    template = _choose(config.speech_templates, rng) or "{target_name}'s public record is notable."
    return AgentDecision.speech(
        player_id=player_id,
        message=_format_template(template, context),
    )


def _vote_decision(
    player_id: str,
    observation: AgentObservation,
    config: FakeLlmConfig,
    rng: random.Random,
) -> AgentDecision:
    scores = _candidate_scores(observation, include_self=False)
    target_id = _weighted_choice(scores, rng, randomness=config.randomness)
    if target_id is None:
        return AgentDecision.pass_(player_id=player_id, reason=MESSAGE_NO_VALID_VOTE_TARGETS)
    return AgentDecision.vote(
        player_id=player_id,
        target_id=target_id,
        reason=_reason(AgentActionType.VOTE, target_id, observation, config, rng),
    )


def _night_decision(
    player_id: str,
    observation: AgentObservation,
    config: FakeLlmConfig,
    rng: random.Random,
) -> AgentDecision:
    if observation.role is AgentRole.WEREWOLF:
        return _werewolf_attack(player_id, observation, config, rng)
    if observation.role is AgentRole.SEER:
        return _seer_inspect(player_id, observation, config, rng)
    if observation.role is AgentRole.KNIGHT:
        return _knight_guard(player_id, observation, config, rng)
    return AgentDecision.pass_(player_id=player_id, reason=MESSAGE_ROLE_HAS_NO_NIGHT_ACTION)


def _werewolf_attack(
    player_id: str,
    observation: AgentObservation,
    config: FakeLlmConfig,
    rng: random.Random,
) -> AgentDecision:
    scores = {
        candidate_id: score
        for candidate_id, score in _candidate_scores(observation, include_self=False).items()
        if observation.known_roles.get(candidate_id) is not AgentRole.WEREWOLF
    }
    target_id = _weighted_choice(scores, rng, randomness=config.randomness)
    if target_id is None:
        return AgentDecision.pass_(player_id=player_id, reason=MESSAGE_NO_ATTACK_TARGETS)
    return AgentDecision.attack(
        player_id=player_id,
        target_id=target_id,
        reason=_reason(AgentActionType.WEREWOLF_ATTACK, target_id, observation, config, rng),
    )


def _seer_inspect(
    player_id: str,
    observation: AgentObservation,
    config: FakeLlmConfig,
    rng: random.Random,
) -> AgentDecision:
    scores = _candidate_scores(observation, include_self=False)
    for candidate_id in list(scores):
        scores[candidate_id] += 3.0 if candidate_id not in observation.known_roles else -1.0
    target_id = _weighted_choice(scores, rng, randomness=config.randomness)
    if target_id is None:
        return AgentDecision.pass_(player_id=player_id, reason=MESSAGE_NO_INSPECT_TARGETS)
    return AgentDecision.inspect(
        player_id=player_id,
        target_id=target_id,
        reason=_reason(AgentActionType.SEER_INSPECT, target_id, observation, config, rng),
    )


def _knight_guard(
    player_id: str,
    observation: AgentObservation,
    config: FakeLlmConfig,
    rng: random.Random,
) -> AgentDecision:
    scores = _candidate_scores(observation, include_self=True)
    scores[player_id] = scores.get(player_id, 1.0) + 0.8
    for candidate_id, vote_count in _received_vote_counts(observation).items():
        if candidate_id in scores:
            scores[candidate_id] += vote_count * 0.3
    target_id = _weighted_choice(scores, rng, randomness=config.randomness)
    if target_id is None:
        return AgentDecision.pass_(player_id=player_id, reason=MESSAGE_NO_GUARD_TARGETS)
    return AgentDecision.guard(
        player_id=player_id,
        target_id=target_id,
        reason=_reason(AgentActionType.KNIGHT_GUARD, target_id, observation, config, rng),
    )


def _candidate_scores(
    observation: AgentObservation,
    *,
    include_self: bool,
) -> dict[str, float]:
    scores = {
        player.id: 1.0
        for player in observation.players
        if player.status is AgentPlayerStatus.ALIVE
        and (include_self or player.id != observation.me.id)
    }
    received_votes = _received_vote_counts(observation)
    speech_counts = Counter(speech.player_id for speech in observation.speeches)
    for candidate_id in list(scores):
        scores[candidate_id] += received_votes.get(candidate_id, 0) * 1.4
        scores[candidate_id] += min(speech_counts.get(candidate_id, 0), 3) * 0.2
    return scores


def _received_vote_counts(observation: AgentObservation) -> Counter[str]:
    counts: Counter[str] = Counter()
    for vote_round in observation.vote_rounds:
        counts.update(vote_round.votes.values())
        counts.update(
            {
                player_id: count
                for player_id, count in vote_round.counts.items()
                if player_id not in vote_round.votes.values()
            }
        )
    return counts


def _weighted_choice(
    scores: Mapping[str, float],
    rng: random.Random,
    *,
    randomness: float,
) -> str | None:
    candidates = [(candidate_id, max(score, 0.0)) for candidate_id, score in sorted(scores.items())]
    if not candidates:
        return None
    jitter = max(0.0, min(randomness, 1.0))
    if jitter == 0:
        return max(candidates, key=lambda item: item[1])[0]
    weighted = [
        (candidate_id, score + 0.01 + rng.random() * jitter) for candidate_id, score in candidates
    ]
    total = sum(score for _candidate_id, score in weighted)
    threshold = rng.random() * total
    current = 0.0
    for candidate_id, score in weighted:
        current += score
        if current >= threshold:
            return candidate_id
    return weighted[-1][0]


def _reason(
    action: AgentActionType,
    target_id: str,
    observation: AgentObservation,
    config: FakeLlmConfig,
    rng: random.Random,
) -> str:
    template = _choose(config.reason_templates, rng) or "fake_llm {action}"
    context = _decision_context(observation, config, rng, action=action, target_id=target_id)
    return _format_template(template, context)


def _decision_context(
    observation: AgentObservation,
    config: FakeLlmConfig,
    rng: random.Random,
    *,
    action: AgentActionType,
    target_id: str | None,
) -> dict[str, object]:
    persona = _choose(config.persona_profiles, rng) or "balanced"
    intent = _choose(config.speech_intents, rng) or "observe"
    target_name = _name_for(observation, target_id)
    return {
        "action": action.value,
        "day": observation.day,
        "intent": intent,
        "persona": persona,
        "phase": observation.phase.value,
        "target_id": target_id or "",
        "target_name": target_name,
    }


def _choose(candidates: Sequence[str], rng: random.Random) -> str | None:
    if not candidates:
        return None
    return rng.choice(tuple(candidates))


def _format_template(template: str, context: Mapping[str, object]) -> str:
    return template.format_map(_SafeFormatContext(context))


class _SafeFormatContext(dict[str, object]):
    def __missing__(self, key: str) -> str:
        return ""


def _name_for(observation: AgentObservation, player_id: str | None) -> str:
    if player_id is None:
        return "everyone"
    for player in observation.players:
        if player.id == player_id:
            return player.name
    return player_id


__all__ = ["choose_fake_llm_decision"]

