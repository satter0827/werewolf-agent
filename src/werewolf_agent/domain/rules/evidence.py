"""公開議論事実を行動根拠候補へ変換する規則."""

from __future__ import annotations

from werewolf_agent.domain.state import EvidenceFact, EvidenceKind, GameState


def public_discussion_evidence(snapshot: GameState) -> tuple[EvidenceFact, ...]:
    """現在の公開履歴から型付き議論根拠を時系列順に返す."""
    facts = [
        EvidenceFact(
            evidence_id=speech.speech_id,
            kind=EvidenceKind.DISCUSSION,
            actor_id=speech.player_id,
            topic_id=speech.topic_id,
            position=speech.position,
        )
        for speech in snapshot.history.speeches
    ]
    facts.extend(
        EvidenceFact(
            evidence_id=f"pass:{result.day}:{result.round_id}:{player_id}",
            kind=EvidenceKind.DISCUSSION_PASS,
            actor_id=player_id,
            topic_id=player_id,
        )
        for result in snapshot.history.discussions
        if result.day == snapshot.day
        for player_id in result.passed_player_ids
    )
    return tuple(facts)


def evidence_concerns_target(fact: EvidenceFact, target_id: str) -> bool:
    """公開事実が投票対象本人または対象命題に関係するか返す."""
    return target_id in {fact.actor_id, fact.topic_id}


__all__ = ["evidence_concerns_target", "public_discussion_evidence"]
