"""LangChain-backed decision services for visible player observations."""

from __future__ import annotations

from hashlib import sha256

from werewolf_agent.adapters.llm.langchain.constants import (
    DEFAULT_REPAIRED_SPEECH,
    DETERMINISTIC_SELECTOR_BYTES,
    LLM_SPEECH_MESSAGE_MAX_CHARS,
)
from werewolf_agent.adapters.llm.messages import (
    MESSAGE_NO_ATTACK_TARGETS,
    MESSAGE_NO_GUARD_TARGETS,
    MESSAGE_NO_INSPECT_TARGETS,
    MESSAGE_NO_TARGET,
    MESSAGE_NO_VALID_VOTE_TARGETS,
)
from werewolf_agent.agents.models import (
    AgentActionType,
    AgentDecision,
    AgentObservation,
    AgentPhase,
    AgentPlayerStatus,
    VisiblePlayer,
)


def _selected_action(observation: AgentObservation) -> AgentActionType:
    if observation.phase is AgentPhase.DAY_DISCUSSION:
        return _first_available(observation, AgentActionType.SPEECH)
    if observation.phase is AgentPhase.VOTING:
        return _first_available(observation, AgentActionType.VOTE)
    if observation.phase is AgentPhase.NIGHT:
        for action_type in (
            AgentActionType.WEREWOLF_ATTACK,
            AgentActionType.SEER_INSPECT,
            AgentActionType.KNIGHT_GUARD,
        ):
            if action_type in observation.available_actions:
                return action_type
    return AgentActionType.PASS


def _first_available(
    observation: AgentObservation,
    action_type: AgentActionType,
) -> AgentActionType:
    return action_type if action_type in observation.available_actions else AgentActionType.PASS


def _target_for_action(
    observation: AgentObservation,
    action_type: AgentActionType,
) -> str | None:
    candidates = _legal_targets_by_action(observation).get(action_type, [])
    if not candidates:
        return None
    selector = _deterministic_target_selector(observation.me.id, observation, action_type)
    return candidates[selector % len(candidates)]


def _ranked_targets_by_action(
    observation: AgentObservation,
    action_type: AgentActionType,
) -> dict[str, list[str]]:
    candidates = list(observation.legal_targets.get(action_type, []))
    if action_type not in AgentDecision.TARGET_TYPES or not candidates:
        return {}
    return {
        action_type.value: sorted(
            candidates,
            key=lambda player_id: (
                -_target_signal(observation, player_id),
                _stable_target_rank(observation, action_type, player_id),
            ),
        )
    }


def _target_signal(observation: AgentObservation, player_id: str) -> int:
    if not observation.vote_rounds:
        return 0
    return int(observation.vote_rounds[-1].counts.get(player_id, 0))


def _stable_target_rank(
    observation: AgentObservation,
    action_type: AgentActionType,
    player_id: str,
) -> int:
    digest = sha256(
        f"{observation.me.id}:{action_type.value}:{observation.day}:{player_id}:rank".encode()
    ).digest()
    return int.from_bytes(digest[:DETERMINISTIC_SELECTOR_BYTES], "big")


def _legal_targets_by_action(
    observation: AgentObservation,
) -> dict[AgentActionType, list[str]]:
    """Return legal target ids for available target-taking actions."""
    targets: dict[AgentActionType, list[str]] = {}
    for action_type in observation.available_actions:
        if action_type not in AgentDecision.TARGET_TYPES:
            continue
        targets[action_type] = list(observation.legal_targets.get(action_type, []))
    return targets


def _fallback_decision(
    player_id: str,
    observation: AgentObservation,
    action_type: AgentActionType,
    *,
    reason: str,
) -> AgentDecision:
    if action_type is AgentActionType.SPEECH and action_type in observation.available_actions:
        return AgentDecision.speech(player_id, _fallback_speech(observation))
    if action_type in AgentDecision.TARGET_TYPES and action_type in observation.available_actions:
        target_id = _target_for_action(observation, action_type)
        if target_id is None:
            return AgentDecision.pass_(
                player_id=player_id,
                reason=_missing_target_reason(action_type),
            )
        return _target_decision(player_id, action_type, target_id, reason=reason)
    return AgentDecision.pass_(player_id=player_id, reason=reason)


def _fallback_speech(observation: AgentObservation) -> str:
    focus = _focus_player(observation)
    if focus is None:
        return DEFAULT_REPAIRED_SPEECH
    return _bounded_speech(f"I want to compare {focus.name}'s claims with the votes.")


def _target_decision(
    player_id: str,
    action_type: AgentActionType,
    target_id: str,
    *,
    reason: str,
) -> AgentDecision:
    if action_type is AgentActionType.VOTE:
        return AgentDecision.vote(player_id, target_id, reason=reason)
    if action_type is AgentActionType.WEREWOLF_ATTACK:
        return AgentDecision.attack(player_id, target_id, reason=reason)
    if action_type is AgentActionType.SEER_INSPECT:
        return AgentDecision.inspect(player_id, target_id, reason=reason)
    if action_type is AgentActionType.KNIGHT_GUARD:
        return AgentDecision.guard(player_id, target_id, reason=reason)
    return AgentDecision.pass_(player_id=player_id, reason=reason)


def _missing_target_reason(action_type: AgentActionType) -> str:
    if action_type is AgentActionType.VOTE:
        return MESSAGE_NO_VALID_VOTE_TARGETS
    if action_type is AgentActionType.WEREWOLF_ATTACK:
        return MESSAGE_NO_ATTACK_TARGETS
    if action_type is AgentActionType.SEER_INSPECT:
        return MESSAGE_NO_INSPECT_TARGETS
    if action_type is AgentActionType.KNIGHT_GUARD:
        return MESSAGE_NO_GUARD_TARGETS
    return MESSAGE_NO_TARGET


def _deterministic_target_selector(
    player_id: str,
    observation: AgentObservation,
    action_type: AgentActionType,
) -> int:
    digest = sha256(f"{player_id}:{action_type.value}:{observation.day}:target".encode()).digest()
    return int.from_bytes(digest[:DETERMINISTIC_SELECTOR_BYTES], "big")


def _focus_player(observation: AgentObservation) -> VisiblePlayer | None:
    candidates = [
        player
        for player in observation.players
        if player.status is AgentPlayerStatus.ALIVE and player.id != observation.me.id
    ]
    if not candidates:
        return None
    selector = _deterministic_target_selector(
        observation.me.id,
        observation,
        AgentActionType.SPEECH,
    )
    return candidates[selector % len(candidates)]


def _bounded_speech(message: str) -> str:
    text = " ".join(message.strip().split())
    if len(text) <= LLM_SPEECH_MESSAGE_MAX_CHARS:
        return text
    return text[:LLM_SPEECH_MESSAGE_MAX_CHARS].rstrip()


def _speech_too_long(decision: AgentDecision) -> bool:
    return (
        decision.type is AgentActionType.SPEECH
        and decision.message is not None
        and len(decision.message) > LLM_SPEECH_MESSAGE_MAX_CHARS
    )
