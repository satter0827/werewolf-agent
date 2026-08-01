"""Tests for request-specific LLM structured-output schemas."""

from jsonschema import Draft202012Validator

from werewolf_agent.adapters.llm.models import AgentObservation
from werewolf_agent.adapters.llm.schemas import build_decision_response_schema


def test_pass_schema_forbids_speech_fields() -> None:
    observation = _observation(actions=[{"type": "pass"}])
    schema = build_decision_response_schema(observation, _context())
    validator = Draft202012Validator(schema)

    assert validator.is_valid({"type": "pass"})
    assert not validator.is_valid({"type": "pass", "message": "見送る", "subject_id": "p2"})


def test_response_schema_requires_one_visible_legal_reference() -> None:
    observation = _observation(
        actions=[{"type": "speech"}],
        legal_subjects={"speech": ["p2", "p3"]},
        legal_references={"speech": ["opening:p2", "opening:p3"]},
    )
    schema = build_decision_response_schema(observation, _context())
    validator = Draft202012Validator(schema)

    assert validator.is_valid(
        {
            "type": "speech",
            "message": "その根拠を確認したい",
            "speech_act": "answer",
            "subject_id": "p2",
            "evidence_id": "opening:p2",
            "response_to_id": "opening:p2",
        }
    )
    assert not validator.is_valid(
        {
            "type": "speech",
            "message": "さらに質問します",
            "speech_act": "question",
            "subject_id": "p2",
            "evidence_id": "opening:p2",
            "response_to_id": "opening:p2",
        }
    )
    assert not validator.is_valid(
        {
            "type": "speech",
            "message": "参照と根拠を混同します",
            "speech_act": "challenge",
            "subject_id": "p2",
            "evidence_id": "opening:p2",
            "response_to_id": "opening:p3",
        }
    )
    assert not validator.is_valid(
        {
            "type": "speech",
            "message": "根拠を確認したい",
            "speech_act": "question",
            "subject_id": "p2",
        }
    )
    assert not validator.is_valid(
        {
            "type": "speech",
            "message": "根拠を確認したい",
            "speech_act": "challenge",
            "subject_id": "p2",
            "evidence_id": "hidden:p4",
            "response_to_id": "hidden:p4",
        }
    )


def test_vote_schema_constrains_target_and_requires_reason() -> None:
    observation = _observation(
        phase="voting",
        actions=[{"type": "vote"}],
        legal_targets={"vote": ["p2"]},
    )
    schema = build_decision_response_schema(observation, _context())
    validator = Draft202012Validator(schema)

    assert validator.is_valid({"type": "vote", "target_id": "p2", "reason": "発言矛盾"})
    assert not validator.is_valid({"type": "vote", "target_id": "p3", "reason": "疑い"})
    assert not validator.is_valid({"type": "vote", "target_id": "p2"})


def test_evidence_based_opening_requires_evidence_for_non_question_act() -> None:
    observation = _observation(
        actions=[{"type": "speech"}],
        legal_subjects={"speech": ["p2"]},
        legal_evidence={"speech": ["speech-1"]},
    )
    validator = Draft202012Validator(build_decision_response_schema(observation, _context()))

    assert validator.is_valid(
        {
            "type": "speech",
            "message": "前日の発言を支持します",
            "speech_act": "support",
            "subject_id": "p2",
            "evidence_id": "speech-1",
        }
    )
    assert not validator.is_valid(
        {
            "type": "speech",
            "message": "根拠なしで支持します",
            "speech_act": "support",
            "subject_id": "p2",
        }
    )


def test_vote_schema_binds_evidence_to_selected_target() -> None:
    observation = _observation(
        phase="voting",
        actions=[{"type": "vote"}],
        legal_targets={"vote": ["p2", "p3"]},
        legal_evidence={"vote": ["speech-p2", "speech-p3"]},
    )
    context = {
        **_context(),
        "public_evidence": [
            {"id": "speech-p2", "actor": {"id": "p2"}, "subject": {"id": "p1"}},
            {"id": "speech-p3", "actor": {"id": "p3"}, "subject": {"id": "p1"}},
        ],
    }
    validator = Draft202012Validator(build_decision_response_schema(observation, context))

    assert validator.is_valid(
        {
            "type": "vote",
            "target_id": "p2",
            "evidence_id": "speech-p2",
            "reason": "p2の発言を根拠に判断します",
        }
    )
    assert not validator.is_valid(
        {
            "type": "vote",
            "target_id": "p2",
            "evidence_id": "speech-p3",
            "reason": "無関係な発言を使います",
        }
    )


def _observation(
    *,
    phase: str = "day_discussion",
    actions: list[dict[str, object]],
    legal_targets: dict[str, list[str]] | None = None,
    legal_subjects: dict[str, list[str]] | None = None,
    legal_evidence: dict[str, list[str]] | None = None,
    legal_references: dict[str, list[str]] | None = None,
) -> AgentObservation:
    return AgentObservation.model_validate(
        {
            "phase": phase,
            "day": 1,
            "me": {"id": "p1", "name": "Alice", "status": "alive"},
            "players": [
                {"id": "p1", "name": "Alice", "status": "alive"},
                {"id": "p2", "name": "Bob", "status": "alive"},
                {"id": "p3", "name": "Carol", "status": "alive"},
            ],
            "available_actions": actions,
            "legal_targets": legal_targets or {},
            "legal_subjects": legal_subjects or {},
            "legal_evidence": legal_evidence or {},
            "legal_references": legal_references or {},
        }
    )


def _context() -> dict[str, object]:
    return {
        "legal": {"constraints": {"speech_max_chars": 80}},
        "evidence": [],
    }
