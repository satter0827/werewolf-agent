"""Contract tests for the shared fake/real decision pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from werewolf_agent.adapters.llm.langchain.service import LangChainDecisionProvider
from werewolf_agent.adapters.llm.model_adapters import FakeDecisionModel
from werewolf_agent.adapters.resources import load_llm_definitions
from werewolf_agent.agents.models import (
    AgentActionType,
    AgentObservation,
    AgentPhase,
    AgentPlayerStatus,
    DeliberationLevel,
    ModelRequest,
    ModelResponse,
    VisiblePlayer,
)
from werewolf_agent.agents.tracing import LlmInvocationTrace

PLAYERS = [
    VisiblePlayer(id="p1", name="Alice", status=AgentPlayerStatus.ALIVE),
    VisiblePlayer(id="p2", name="Bob", status=AgentPlayerStatus.ALIVE),
    VisiblePlayer(id="p3", name="Chika", status=AgentPlayerStatus.ALIVE),
]


def observation(
    *,
    action: AgentActionType = AgentActionType.VOTE,
    phase: AgentPhase = AgentPhase.VOTING,
    speeches: int = 0,
) -> AgentObservation:
    targets = [] if action in {AgentActionType.SPEECH, AgentActionType.PASS} else ["p2", "p3"]
    return AgentObservation.model_validate(
        {
            "phase": phase,
            "day": 2,
            "me": PLAYERS[0],
            "role": "villager",
            "players": PLAYERS,
            "available_actions": [action],
            "legal_targets": {action: targets} if targets else {},
            "speeches": [
                {"day": 1, "player_id": "p2", "message": f"public claim {index}"}
                for index in range(speeches)
            ],
        }
    )


@dataclass
class StaticDecisionModel:
    content: str
    usage: dict[str, int] = field(default_factory=dict)
    calls: list[ModelRequest] = field(default_factory=list)

    def invoke(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        return ModelResponse(
            content=self.content,
            provider="stub",
            model="stub-model",
            usage=self.usage,
        )


class RecordingTraceSink:
    def __init__(self) -> None:
        self.records: list[LlmInvocationTrace] = []

    def record_invocation(self, trace: LlmInvocationTrace) -> None:
        self.records.append(trace)


def provider(
    model: object | None = None,
    *,
    level: DeliberationLevel = DeliberationLevel.STANDARD,
    trace_sink: RecordingTraceSink | None = None,
) -> LangChainDecisionProvider:
    definitions = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    )
    decision_model = model or FakeDecisionModel(definitions.fake_responses)
    return LangChainDecisionProvider(
        prompt=definitions.prompt,
        decision_model=decision_model,  # type: ignore[arg-type]
        provider_name="fake" if model is None else "stub",
        model_name="fake-list-chat-model" if model is None else "stub-model",
        max_output_tokens=128,
        deliberation_level=level,
        trace_sink=trace_sink,
    )


def test_prompt_has_one_compact_context_variable_and_model_decision_schema() -> None:
    prompt = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    ).prompt

    assert prompt.input_variables == ["decision_context_json"]
    assert prompt.response_format == {"schema": "AgentModelDecision"}
    assert "legal.actions" in prompt.messages[0].content
    assert "player_id" in prompt.messages[0].content


@pytest.mark.parametrize(
    ("action", "phase"),
    [
        (AgentActionType.VOTE, AgentPhase.VOTING),
        (AgentActionType.WEREWOLF_ATTACK, AgentPhase.NIGHT),
        (AgentActionType.SEER_INSPECT, AgentPhase.NIGHT),
        (AgentActionType.KNIGHT_GUARD, AgentPhase.NIGHT),
        (AgentActionType.APOTHECARY_HEAL, AgentPhase.NIGHT),
        (AgentActionType.APOTHECARY_POISON, AgentPhase.NIGHT),
    ],
)
def test_fake_chat_model_returns_a_legal_targeted_decision(
    action: AgentActionType,
    phase: AgentPhase,
) -> None:
    decision = provider().choose_decision("p1", observation(action=action, phase=phase))

    assert decision.type is action
    assert decision.player_id == "p1"
    assert decision.target_id in {"p2", "p3"}


def test_fake_chat_model_receives_the_same_legal_contract_as_real_models() -> None:
    definitions = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    )
    fake = FakeDecisionModel(definitions.fake_responses)
    decision_provider = provider(fake)

    decision = decision_provider.choose_decision("p1", observation())

    assert decision.type is AgentActionType.VOTE
    # FakeDecisionModel rejects a checksum mismatch or a context missing from the rendered prompt.


@pytest.mark.parametrize(
    "content",
    [
        "",
        "not json",
        "{}",
        '{"type":"vote","target_id":"p2","reason":"x"',
        'answer: {"type":"vote","target_id":"p2","reason":"x"}',
        '```python\n{"type":"vote","target_id":"p2","reason":"x"}\n```',
    ],
)
def test_invalid_response_uses_one_deterministic_fallback(content: str) -> None:
    model = StaticDecisionModel(content)
    first = provider(model).choose_decision("p1", observation())
    second = provider(StaticDecisionModel(content)).choose_decision("p1", observation())

    assert len(model.calls) == 1
    assert first == second
    assert first.type is AgentActionType.VOTE
    assert first.target_id in {"p2", "p3"}


def test_markdown_fence_is_the_only_semantic_free_normalization() -> None:
    model = StaticDecisionModel(
        '```json\n{"type":"vote","target_id":"p2","reason":"public evidence"}\n```'
    )

    decision = provider(model).choose_decision("p1", observation())

    assert decision.type is AgentActionType.VOTE
    assert decision.target_id == "p2"


def test_public_speech_references_are_retained_in_the_validated_decision() -> None:
    model = StaticDecisionModel(
        '{"type":"speech","message":"確認します。","focus_id":"p2","evidence_id":"speech:d1:p2:1"}'
    )

    decision = provider(model).choose_decision(
        "p1",
        observation(
            action=AgentActionType.SPEECH,
            phase=AgentPhase.DAY_DISCUSSION,
            speeches=1,
        ),
    )

    assert decision.focus_id == "p2"
    assert decision.evidence_id == "speech:d1:p2:1"


def test_prompt_requires_exactly_one_decision_context_marker() -> None:
    definitions = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    )
    prompt = definitions.prompt.model_copy(
        update={
            "messages": tuple(
                message.model_copy(update={"content": "static"})
                for message in definitions.prompt.messages
            )
        }
    )

    with pytest.raises(ValueError, match="exactly once"):
        LangChainDecisionProvider(
            prompt=prompt,
            decision_model=StaticDecisionModel("{}"),
            provider_name="stub",
            model_name="stub-model",
            max_output_tokens=128,
        )


@pytest.mark.parametrize(
    "content",
    [
        '{"type":"seer_inspect","target_id":"p2"}',
        '{"type":"vote","target_id":"missing"}',
        '{"type":"vote","target_id":"p2","focus_id":"secret"}',
        '{"type":"vote","target_id":"p2","evidence_id":"secret"}',
    ],
)
def test_illegal_values_are_not_rewritten_and_enter_fallback(content: str) -> None:
    trace_sink = RecordingTraceSink()
    decision = provider(StaticDecisionModel(content), trace_sink=trace_sink).choose_decision(
        "p1", observation(speeches=1)
    )

    assert decision.type is AgentActionType.VOTE
    assert trace_sink.records[0].fallback_used is True
    assert trace_sink.records[0].validation_status == "fallback"


def test_deliberation_level_only_changes_visible_history_and_output_limit() -> None:
    models = {
        level: StaticDecisionModel('{"type":"speech","message":"確認します。"}')
        for level in DeliberationLevel
    }
    limits = {
        DeliberationLevel.QUICK: (6, 96),
        DeliberationLevel.STANDARD: (16, 96),
        DeliberationLevel.DEEP: (32, 128),
    }

    for level, model in models.items():
        provider(model, level=level).choose_decision(
            "p1",
            observation(
                action=AgentActionType.SPEECH, phase=AgentPhase.DAY_DISCUSSION, speeches=40
            ),
        )
        request = model.calls[0]
        context = json.loads(request.messages[-1].content)
        expected_events, expected_tokens = limits[level]
        assert len(context["evidence"]) == expected_events
        assert request.task.output_token_limit == expected_tokens
        assert len(model.calls) == 1


def test_trace_records_prompt_size_usage_and_annotations_without_estimating() -> None:
    trace_sink = RecordingTraceSink()
    model = StaticDecisionModel(
        '{"type":"vote","target_id":"p2","evidence_id":"speech:d1:p2:1","reason":"発言との整合を確認したため"}',
        usage={"input_tokens": 31, "output_tokens": 9, "total_tokens": 40},
    )

    provider(model, trace_sink=trace_sink).choose_decision("p1", observation(speeches=1))

    trace = trace_sink.records[0]
    assert trace.input_tokens == 31
    assert trace.total_tokens == 40
    assert trace.prompt_characters > 0
    assert trace.request_payload["deliberation_level"] == "standard"
    assert trace.request_payload["evidence_id"] == "speech:d1:p2:1"


def test_trace_records_the_normalization_that_was_applied() -> None:
    trace_sink = RecordingTraceSink()
    model = StaticDecisionModel(
        '```json\n{"type":"vote","target_id":"p2","reason":"public evidence"}\n```'
    )

    provider(model, trace_sink=trace_sink).choose_decision("p1", observation())

    assert trace_sink.records[0].request_payload["normalization"] == "markdown_fence_removed"


def test_evidence_keeps_revote_results_in_chronological_order() -> None:
    model = StaticDecisionModel('{"type":"speech","message":"確認します。"}')
    value = AgentObservation.model_validate(
        {
            **observation(
                action=AgentActionType.SPEECH,
                phase=AgentPhase.DAY_DISCUSSION,
                speeches=1,
            ).model_dump(mode="json"),
            "vote_rounds": [
                {
                    "day": 1,
                    "votes": {"p1": "p2", "p2": "p1"},
                    "counts": {"p1": 1, "p2": 1},
                },
                {
                    "day": 1,
                    "votes": {"p1": "p3"},
                    "counts": {"p3": 1},
                    "eliminated_player_id": "p3",
                },
            ],
        }
    )

    provider(model).choose_decision("p1", value)

    context = json.loads(model.calls[0].messages[-1].content)
    assert [item["id"] for item in context["evidence"]] == [
        "speech:d1:p2:1",
        "vote:d1:r1:p1",
        "vote:d1:r1:p2",
        "vote_result:d1:r1",
        "vote:d1:r2:p1",
        "vote_result:d1:r2",
    ]
    assert context["public_position"]["current_suspicion_id"] == "p3"


def test_only_pass_skips_the_model_call() -> None:
    model = StaticDecisionModel("not used")

    decision = provider(model).choose_decision("p1", observation(action=AgentActionType.PASS))

    assert decision.type is AgentActionType.PASS
    assert model.calls == []
