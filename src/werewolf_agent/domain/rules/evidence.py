"""公開議論事実を行動根拠候補へ変換する規則."""

from __future__ import annotations

from werewolf_agent.domain.state import EvidenceFact, EvidenceKind, GameState


def public_discussion_evidence(snapshot: GameState) -> tuple[EvidenceFact, ...]:
    """現在の公開履歴から型付き議論根拠を時系列順に返す."""
    speeches = {speech.speech_id: speech for speech in snapshot.history.speeches}
    emitted_speech_ids: set[str] = set()
    facts: list[EvidenceFact] = []
    for result in snapshot.history.discussions:
        round_speeches = {
            speeches[speech_id].player_id: speeches[speech_id] for speech_id in result.speech_ids
        }
        passed_player_ids = set(result.passed_player_ids)
        for player_id in result.actor_ids:
            speech = round_speeches.get(player_id)
            if speech is not None:
                emitted_speech_ids.add(speech.speech_id)
                facts.append(
                    EvidenceFact(
                        evidence_id=speech.speech_id,
                        kind=EvidenceKind.DISCUSSION,
                        actor_id=speech.player_id,
                        topic_id=speech.topic_id,
                        position=speech.position,
                    )
                )
            elif player_id in passed_player_ids:
                if result.day == snapshot.day:
                    facts.append(
                        EvidenceFact(
                            evidence_id=f"pass:{result.day}:{result.round_id}:{player_id}",
                            kind=EvidenceKind.DISCUSSION_PASS,
                            actor_id=player_id,
                            topic_id=player_id,
                        )
                    )
            else:
                raise ValueError("discussion result actor must have a speech or pass")
    if set(speeches) != emitted_speech_ids:
        raise ValueError("speech history must belong to a resolved discussion round")
    return tuple(facts)


def evidence_concerns_target(fact: EvidenceFact, target_id: str) -> bool:
    """公開事実が投票対象本人または対象命題に関係するか返す."""
    return target_id in {fact.actor_id, fact.topic_id}


__all__ = ["evidence_concerns_target", "public_discussion_evidence"]
