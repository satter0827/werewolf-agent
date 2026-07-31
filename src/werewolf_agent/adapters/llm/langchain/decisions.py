"""LangChain-backed decision services for visible player observations."""

from __future__ import annotations

from hashlib import sha256

from werewolf_agent.adapters.llm.langchain.constants import (
    DEFAULT_FALLBACK_SPEECH,
    DETERMINISTIC_SELECTOR_BYTES,
    LLM_SPEECH_MESSAGE_MAX_CHARS,
)
from werewolf_agent.adapters.llm.messages import (
    MESSAGE_NO_TARGET,
    MESSAGE_NO_VALID_VOTE_TARGETS,
)
from werewolf_agent.adapters.llm.models import (
    AgentActionType,
    AgentAvailableAction,
    AgentDecision,
    AgentObservation,
    AgentPlayerStatus,
    VisiblePlayer,
)


def _target_for_action(
    observation: AgentObservation,
    action: AgentAvailableAction,
) -> str | None:
    candidates = _legal_targets_by_action(observation).get(action.key, [])
    if not candidates:
        return None
    selector = _deterministic_target_selector(observation.me.id, observation, action.key)
    return candidates[selector % len(candidates)]


def _legal_targets_by_action(
    observation: AgentObservation,
) -> dict[str, list[str]]:
    """Return legal target ids for available target-taking actions."""
    targets: dict[str, list[str]] = {}
    for action in observation.available_actions:
        if action.type not in AgentDecision.TARGET_TYPES:
            continue
        targets[action.key] = list(observation.legal_targets.get(action.key, []))
    return targets


def _fallback_decision(
    player_id: str,
    observation: AgentObservation,
    action: AgentAvailableAction,
    *,
    reason: str,
) -> AgentDecision:
    if action.type is AgentActionType.SPEECH and action in observation.available_actions:
        return AgentDecision.speech(player_id, _fallback_speech(observation))
    if action.type in AgentDecision.TARGET_TYPES and action in observation.available_actions:
        target_id = _target_for_action(observation, action)
        if target_id is None:
            return AgentDecision.pass_(
                player_id=player_id,
                reason=_missing_target_reason(action.type),
            )
        return _target_decision(player_id, action, target_id, reason=reason)
    return AgentDecision.pass_(player_id=player_id, reason=reason)


def _fallback_speech(observation: AgentObservation) -> str:
    focus = _focus_player(observation)
    if focus is None:
        return DEFAULT_FALLBACK_SPEECH
    return _bounded_speech(f"I want to compare {focus.name}'s claims with the votes.")


def _target_decision(
    player_id: str,
    action: AgentAvailableAction,
    target_id: str,
    *,
    reason: str,
) -> AgentDecision:
    if action.type is AgentActionType.VOTE:
        return AgentDecision.vote(player_id, target_id, reason=reason)
    if action.type is AgentActionType.USE_ABILITY and action.ability_id is not None:
        return AgentDecision.use_ability(player_id, action.ability_id, target_id, reason=reason)
    return AgentDecision.pass_(player_id=player_id, reason=reason)


def _missing_target_reason(action_type: AgentActionType) -> str:
    if action_type is AgentActionType.VOTE:
        return MESSAGE_NO_VALID_VOTE_TARGETS
    return MESSAGE_NO_TARGET


def _deterministic_target_selector(
    player_id: str,
    observation: AgentObservation,
    action_key: str,
) -> int:
    digest = sha256(f"{player_id}:{action_key}:{observation.day}:target".encode()).digest()
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
        AgentActionType.SPEECH.value,
    )
    return candidates[selector % len(candidates)]


def _bounded_speech(message: str) -> str:
    text = " ".join(message.strip().split())
    if len(text) <= LLM_SPEECH_MESSAGE_MAX_CHARS:
        return text
    return text[:LLM_SPEECH_MESSAGE_MAX_CHARS].rstrip()
