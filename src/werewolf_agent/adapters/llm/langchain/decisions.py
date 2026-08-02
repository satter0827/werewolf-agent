"""LangChain-backed decision services for visible player observations."""

from __future__ import annotations

from hashlib import sha256

from werewolf_agent.adapters.llm.langchain.constants import (
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
    AgentDiscussionPosition,
    AgentDiscussionRelation,
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
        subject = _focus_player(observation)
        if subject is None:
            return AgentDecision.pass_(player_id=player_id, reason=reason)
        references = observation.legal_references.get(action.key, [])
        reference_id = references[0] if references else None
        evidence = observation.evidence_options.get(action.key, [])
        evidence_id = reference_id or (evidence[-1].id if evidence else None)
        topic_id = subject.id
        position = AgentDiscussionPosition.SUPPORT
        relation = AgentDiscussionRelation.INDEPENDENT
        if reference_id is not None:
            referenced = next(
                speech for speech in observation.speeches if speech.speech_id == reference_id
            )
            topic_id = referenced.topic_id
            if referenced.position is AgentDiscussionPosition.UNDECIDED:
                relation = AgentDiscussionRelation.ANSWER
            else:
                relation = AgentDiscussionRelation.CHALLENGE
                position = (
                    AgentDiscussionPosition.OPPOSE
                    if referenced.position is AgentDiscussionPosition.SUPPORT
                    else AgentDiscussionPosition.SUPPORT
                )
        return AgentDecision.speech(
            player_id,
            _fallback_speech(subject),
            topic_id=topic_id,
            position=position,
            relation=relation,
            evidence_id=evidence_id,
            response_to_id=reference_id,
        )
    if action.type in AgentDecision.TARGET_TYPES and action in observation.available_actions:
        target_id = _target_for_action(observation, action)
        if target_id is None:
            return AgentDecision.pass_(
                player_id=player_id,
                reason=_missing_target_reason(action.type),
            )
        return _target_decision(
            player_id,
            observation,
            action,
            target_id,
            reason=reason,
        )
    return AgentDecision.pass_(player_id=player_id, reason=reason)


def _fallback_speech(subject: VisiblePlayer) -> str:
    return _bounded_speech(f"{subject.name}さんの判断根拠を確認したいです。")


def _target_decision(
    player_id: str,
    observation: AgentObservation,
    action: AgentAvailableAction,
    target_id: str,
    *,
    reason: str,
) -> AgentDecision:
    if action.type is AgentActionType.VOTE:
        evidence = observation.evidence_options.get(action.key, [])
        evidence_id = next(
            (item.id for item in reversed(evidence) if target_id in {item.actor_id, item.topic_id}),
            None,
        )
        return AgentDecision.vote(
            player_id,
            target_id,
            reason=reason,
            evidence_id=evidence_id,
        )
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
