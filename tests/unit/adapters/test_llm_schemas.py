"""Tests for request-specific LLM structured-output schemas."""

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from werewolf_agent.adapters.llm.langchain.service import (
    _normalized_utterance as adapter_normalized_utterance,
)
from werewolf_agent.adapters.llm.models import (
    AgentDecision,
    AgentModelDecision,
    AgentObservation,
    AgentSpeech,
)
from werewolf_agent.adapters.llm.schemas import (
    _normalized_utterance_pattern,
    build_decision_response_schema,
)
from werewolf_agent.agents import DecisionResponse
from werewolf_agent.domain import Action
from werewolf_agent.domain.rules.discussion import _normalized_message
from werewolf_agent.simulation.session import (
    _normalized_utterance as simulation_normalized_utterance,
)


def test_pass_schema_forbids_speech_fields() -> None:
    observation = _observation(actions=[{"type": "pass"}])
    schema = build_decision_response_schema(observation, _context())
    validator = Draft202012Validator(schema)

    assert validator.is_valid({"type": "pass"})
    assert not validator.is_valid({"type": "pass", "utterance": "見送る", "topic_id": "p2"})


def test_response_schema_requires_one_visible_legal_reference() -> None:
    observation = _observation(
        actions=[{"type": "speech"}],
        legal_topics={"speech": ["p2", "p3"]},
        evidence_options={
            "speech": [
                _evidence("opening:p2", "p2", "p3", "undecided"),
                _evidence("opening:p3", "p3", "p2", "support"),
            ]
        },
        legal_references={"speech": ["opening:p2", "opening:p3"]},
        speeches=[
            _speech(
                "opening:p2",
                "p2",
                "p3",
                "undecided",
                utterance="Claim  is true",
            ),
            _speech("opening:p3", "p3", "p2", "support"),
        ],
    )
    schema = build_decision_response_schema(observation, _context())
    validator = Draft202012Validator(schema)

    assert validator.is_valid(
        {
            "type": "speech",
            "utterance": "その根拠を確認したい",
            "topic_id": "p3",
            "position": "support",
            "relation": "answer",
            "evidence_id": "opening:p2",
            "response_to_id": "opening:p2",
        }
    )
    assert not validator.is_valid(
        {
            "type": "speech",
            "utterance": " claim is true ",
            "topic_id": "p3",
            "position": "support",
            "relation": "answer",
            "evidence_id": "opening:p2",
            "response_to_id": "opening:p2",
        }
    )
    assert not validator.is_valid(
        {
            "type": "speech",
            "utterance": "さらに質問します",
            "topic_id": "p3",
            "position": "undecided",
            "relation": "independent",
            "evidence_id": "opening:p2",
            "response_to_id": "opening:p2",
        }
    )
    assert not validator.is_valid(
        {
            "type": "speech",
            "utterance": "参照と根拠を混同します",
            "topic_id": "p3",
            "position": "oppose",
            "relation": "challenge",
            "evidence_id": "opening:p2",
            "response_to_id": "opening:p3",
        }
    )
    assert not validator.is_valid(
        {
            "type": "speech",
            "utterance": "根拠を確認したい",
            "topic_id": "p2",
            "position": "undecided",
            "relation": "independent",
        }
    )
    assert not validator.is_valid(
        {
            "type": "speech",
            "utterance": "根拠を確認したい",
            "topic_id": "p2",
            "position": "oppose",
            "relation": "challenge",
            "evidence_id": "hidden:p4",
            "response_to_id": "hidden:p4",
        }
    )


def test_response_schema_uses_only_relations_authorized_by_setup() -> None:
    observation = _observation(
        actions=[{"type": "speech"}],
        legal_topics={"speech": ["p3"]},
        evidence_options={"speech": [_evidence("opening:p2", "p2", "p3", "undecided")]},
        legal_references={"speech": ["opening:p2"]},
        legal_relations={"speech": ["support"]},
        speeches=[_speech("opening:p2", "p2", "p3", "undecided")],
    )
    validator = Draft202012Validator(build_decision_response_schema(observation, _context()))

    base = {
        "type": "speech",
        "utterance": "判断保留という立場を支持します",
        "topic_id": "p3",
        "evidence_id": "opening:p2",
        "response_to_id": "opening:p2",
    }
    assert validator.is_valid({**base, "position": "undecided", "relation": "support"})
    assert not validator.is_valid({**base, "position": "support", "relation": "answer"})


def test_repetition_normalization_is_consistent_and_schema_expressible() -> None:
    normalizers = (
        adapter_normalized_utterance,
        simulation_normalized_utterance,
        _normalized_message,
    )

    for normalize in normalizers:
        assert normalize("Claim  is true") == normalize(" claim is TRUE ")
        assert normalize("Claim\tis\ntrue") == normalize(" claim is TRUE ")
        assert normalize("A B") != normalize("A\u001cB")
        assert normalize("A B") != normalize("A\ufeffB")
        assert normalize("STRASSE") != normalize("straße")
        assert normalize("ΟΣ") != normalize("ος")

    observation = _observation(
        actions=[{"type": "speech"}],
        legal_topics={"speech": ["p3"]},
        evidence_options={"speech": [_evidence("opening:p2", "p2", "p3", "support")]},
        legal_references={"speech": ["opening:p2"]},
        legal_relations={"speech": ["support"]},
        speeches=[
            _speech(
                "opening:p2",
                "p2",
                "p3",
                "support",
                utterance="STRASSE",
            )
        ],
    )
    validator = Draft202012Validator(build_decision_response_schema(observation, _context()))

    assert validator.is_valid(
        {
            "type": "speech",
            "utterance": "straße",
            "topic_id": "p3",
            "position": "support",
            "relation": "support",
            "evidence_id": "opening:p2",
            "response_to_id": "opening:p2",
        }
    )

    whitespace_observation = _observation(
        actions=[{"type": "speech"}],
        legal_topics={"speech": ["p3"]},
        evidence_options={"speech": [_evidence("opening:p2", "p2", "p3", "support")]},
        legal_references={"speech": ["opening:p2"]},
        legal_relations={"speech": ["support"]},
        speeches=[_speech("opening:p2", "p2", "p3", "support", utterance="Claim")],
    )
    whitespace_validator = Draft202012Validator(
        build_decision_response_schema(whitespace_observation, _context())
    )
    response = {
        "type": "speech",
        "topic_id": "p3",
        "position": "support",
        "relation": "support",
        "evidence_id": "opening:p2",
        "response_to_id": "opening:p2",
    }
    assert not whitespace_validator.is_valid({**response, "utterance": " Claim\t"})
    assert whitespace_validator.is_valid({**response, "utterance": "Claim\u001c"})
    assert whitespace_validator.is_valid({**response, "utterance": "Claim\ufeff"})


def test_non_contract_edge_whitespace_is_preserved_across_decision_boundaries() -> None:
    utterance = "Claim\u001c"
    model_payload = {
        "type": "speech",
        "utterance": utterance,
        "topic_id": "p2",
        "position": "support",
        "relation": "independent",
    }

    assert AgentModelDecision.model_validate(model_payload).utterance == utterance
    assert (
        AgentDecision.speech(
            "p1",
            utterance,
            topic_id="p2",
            position="support",
            relation="independent",
        ).utterance
        == utterance
    )
    assert (
        AgentSpeech(
            day=1,
            speech_id="speech-1",
            player_id="p1",
            utterance=utterance,
            topic_id="p2",
            position="support",
            relation="independent",
        ).utterance
        == utterance
    )
    assert (
        DecisionResponse(
            "speech",
            utterance=utterance,
            topic_id="p2",
            position="support",
            relation="independent",
        ).utterance
        == utterance
    )
    assert (
        Action.speech(
            "p1",
            utterance,
            topic_id="p2",
            position="support",
            relation="independent",
        ).utterance
        == utterance
    )

    with pytest.raises((ValidationError, ValueError), match="utterance must not be blank"):
        AgentModelDecision.model_validate({**model_payload, "utterance": " \t\n"})


@pytest.mark.parametrize(
    ("utterance", "escaped"),
    [
        ("CO-2", r"\x2D"),
        ("A#B", r"\x23"),
        ("A&B", r"\x26"),
        ("A~B", r"\x7E"),
        ("A[B]", r"\x5B"),
        (r"A\B", r"\x5C"),
    ],
)
def test_response_repetition_pattern_uses_ecmascript_safe_escapes(
    utterance: str,
    escaped: str,
) -> None:
    """ECMA-262 Unicode modeで不正なidentity escapeを生成しない."""
    pattern = _normalized_utterance_pattern(utterance)

    assert escaped in pattern
    assert not any(f"\\{character}" in pattern for character in "-#&~")


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


def test_opening_constrains_structured_semantics_and_optional_evidence() -> None:
    observation = _observation(
        actions=[{"type": "speech"}],
        legal_topics={"speech": ["p2"]},
        evidence_options={"speech": [_evidence("speech-1", "p2", "p2", "support")]},
    )
    validator = Draft202012Validator(build_decision_response_schema(observation, _context()))

    assert validator.is_valid(
        {
            "type": "speech",
            "utterance": "前日の発言を踏まえます",
            "topic_id": "p2",
            "position": "support",
            "relation": "independent",
            "evidence_id": "speech-1",
        }
    )
    assert not validator.is_valid(
        {
            "type": "speech",
            "utterance": "不正な根拠を使います",
            "topic_id": "p2",
            "position": "support",
            "relation": "independent",
            "evidence_id": "hidden",
        }
    )


def test_vote_schema_binds_evidence_to_selected_target() -> None:
    observation = _observation(
        phase="voting",
        actions=[{"type": "vote"}],
        legal_targets={"vote": ["p2", "p3"]},
        evidence_options={
            "vote": [
                _evidence("speech-p2", "p2", "p1", "support"),
                _evidence("speech-p3", "p3", "p1", "support"),
            ]
        },
    )
    context = {
        **_context(),
        "argument_ledger": [],
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
    legal_topics: dict[str, list[str]] | None = None,
    evidence_options: dict[str, list[dict[str, object]]] | None = None,
    legal_references: dict[str, list[str]] | None = None,
    legal_relations: dict[str, list[str]] | None = None,
    speeches: list[dict[str, object]] | None = None,
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
            "legal_topics": legal_topics or {},
            "evidence_options": evidence_options or {},
            "legal_references": legal_references or {},
            "legal_relations": legal_relations
            or {"speech": ["answer", "support", "challenge", "revise"]},
            "speeches": speeches or [],
        }
    )


def _context() -> dict[str, object]:
    return {
        "legal": {"constraints": {"speech_max_chars": 80}},
        "evidence": [],
    }


def _evidence(evidence_id: str, actor_id: str, topic_id: str, position: str) -> dict[str, object]:
    return {
        "id": evidence_id,
        "kind": "discussion",
        "actor_id": actor_id,
        "topic_id": topic_id,
        "position": position,
    }


def _speech(
    speech_id: str,
    player_id: str,
    topic_id: str,
    position: str,
    *,
    utterance: str | None = None,
) -> dict[str, object]:
    return {
        "day": 1,
        "speech_id": speech_id,
        "player_id": player_id,
        "utterance": utterance or f"{speech_id}の発言",
        "topic_id": topic_id,
        "position": position,
        "relation": "independent",
    }
