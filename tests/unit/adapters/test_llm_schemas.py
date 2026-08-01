"""Tests for request-specific LLM structured-output schemas."""

from jsonschema import Draft202012Validator

from werewolf_agent.adapters.llm.models import AgentObservation
from werewolf_agent.adapters.llm.schemas import build_decision_response_schema


def test_pass_schema_forbids_speech_fields() -> None:
    observation = _observation(actions=[{"type": "pass"}])
    schema = build_decision_response_schema(observation, _context())
    validator = Draft202012Validator(schema)

    assert validator.is_valid({"type": "pass", "reason": "様子を見る"})
    assert not validator.is_valid({"type": "pass", "message": "見送る", "focus_id": "p2"})


def test_response_schema_requires_one_visible_legal_reference() -> None:
    observation = _observation(
        actions=[{"type": "speech"}],
        legal_references={"speech": ["opening:p2", "opening:p3"]},
    )
    schema = build_decision_response_schema(observation, _context())
    validator = Draft202012Validator(schema)

    assert validator.is_valid(
        {
            "type": "speech",
            "message": "その根拠を確認したい",
            "response_to_id": "opening:p2",
        }
    )
    assert not validator.is_valid({"type": "speech", "message": "根拠を確認したい"})
    assert not validator.is_valid(
        {
            "type": "speech",
            "message": "根拠を確認したい",
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


def _observation(
    *,
    phase: str = "day_discussion",
    actions: list[dict[str, object]],
    legal_targets: dict[str, list[str]] | None = None,
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
            "legal_references": legal_references or {},
        }
    )


def _context() -> dict[str, object]:
    return {
        "legal": {"constraints": {"speech_max_chars": 80}},
        "evidence": [],
    }
