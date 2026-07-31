"""標準ライブラリAgent SDKの外部注入契約を検証する."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from werewolf_agent.agents import (
    AgentContext,
    AgentObservation,
    AgentSession,
    AgentSpec,
    DecisionOption,
    DecisionRequest,
    DecisionResponse,
    DecisionTrace,
    ObservedPlayer,
    PublicTimelineEvent,
    RandomLegalAgentFactory,
)


class _Session:
    def __init__(self, context: AgentContext) -> None:
        self.context = context
        self.closed = False

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        assert request.context == self.context
        return DecisionResponse(action_type=request.options[0].action_type)

    def close(self) -> None:
        self.closed = True


class _Factory:
    @property
    def spec(self) -> AgentSpec:
        return AgentSpec("external", "1.0.0", "1" * 64, {"mode": "test"})

    def create(self, context: AgentContext) -> AgentSession:
        return _Session(context)


def _request(context: AgentContext) -> DecisionRequest:
    me = ObservedPlayer(context.player_id, "Alice", True)
    other = ObservedPlayer("p2", "Bob", True)
    return DecisionRequest(
        decision_id="decision-1",
        context=context,
        observation=AgentObservation(
            phase="voting",
            day=1,
            me=me,
            players=(me, other),
            known_roles={context.player_id: "villager"},
        ),
        public_timeline=(PublicTimelineEvent(1, "speech", 1, "p2", {"message": ["確認します"]}),),
        options=(DecisionOption("vote", legal_target_ids=("p2",)),),
        decision_seed=17,
        deadline_at=datetime(2030, 1, 1, tzinfo=UTC),
    )


def test_external_factory_creates_state_isolated_sessions() -> None:
    factory = _Factory()
    first_context = AgentContext("s1", "g1", "p1", 11)
    second_context = AgentContext("s2", "g1", "p2", 12)

    first = factory.create(first_context)
    second = factory.create(second_context)

    assert isinstance(first, AgentSession)
    assert first is not second
    assert first.decide(_request(first_context)).action_type == "vote"


def test_request_rejects_secret_or_illegal_player_references() -> None:
    context = AgentContext("s1", "g1", "p1", 11)
    me = ObservedPlayer("p1", "Alice", True)

    with pytest.raises(ValueError, match="visible players"):
        AgentObservation(
            phase="voting",
            day=1,
            me=me,
            players=(me,),
            known_roles={"secret-player": "werewolf"},
        )
    with pytest.raises(ValueError, match="legal targets"):
        DecisionRequest(
            decision_id="decision-1",
            context=context,
            observation=AgentObservation("voting", 1, me, (me,)),
            public_timeline=(),
            options=(DecisionOption("vote", legal_target_ids=("secret-player",)),),
            decision_seed=17,
        )
    with pytest.raises(ValueError, match="timeline actors"):
        DecisionRequest(
            decision_id="decision-1",
            context=context,
            observation=AgentObservation("voting", 1, me, (me,)),
            public_timeline=(PublicTimelineEvent(1, "speech", 1, "secret-player"),),
            options=(DecisionOption("pass"),),
            decision_seed=17,
        )


def test_contract_values_deeply_freeze_diagnostics_and_public_payloads() -> None:
    spec = AgentSpec("external", "1.0.0", "1" * 64, {"nested": {"items": [1, 2]}})
    request = _request(AgentContext("s1", "g1", "p1", 11))

    assert spec.parameters["nested"] == {"items": (1, 2)}
    assert request.public_timeline[0].payload["message"] == ("確認します",)
    with pytest.raises(TypeError):
        spec.parameters["other"] = True  # type: ignore[index]
    with pytest.raises(ValueError, match="mapping keys"):
        AgentSpec("external", "1.0.0", "1" * 64, {1: "invalid"})  # type: ignore[dict-item]
    with pytest.raises(ValueError, match="JSON-compatible"):
        AgentSpec("external", "1.0.0", "1" * 64, {"runtime": object()})


def test_contract_rejects_non_string_text_without_leaking_attribute_errors() -> None:
    """外部実装の型違反を一貫した契約エラーとして拒否する."""
    with pytest.raises(ValueError, match="agent_id must be a string"):
        AgentSpec(1, "1.0.0", "1" * 64)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="speech must be a string"):
        RandomLegalAgentFactory(1)  # type: ignore[arg-type]


def test_decision_trace_requires_an_outcome_and_a_fallback_response() -> None:
    """分析不能な空traceと応答のないfallbackを拒否する."""
    spec = AgentSpec("external", "1.0.0", "1" * 64)
    with pytest.raises(ValueError, match="response or error_code"):
        DecisionTrace("decision-1", spec, None, 1)
    with pytest.raises(ValueError, match="fallback trace must contain a response"):
        DecisionTrace("decision-1", spec, None, 1, True, "agent_timeout")
    with pytest.raises(ValueError, match="fallback trace must contain an error_code"):
        DecisionTrace("decision-1", spec, DecisionResponse("pass"), 1, True)
    with pytest.raises(ValueError, match="successful trace must not contain an error_code"):
        DecisionTrace("decision-1", spec, DecisionResponse("pass"), 1, False, "agent_fault")

    response = DecisionResponse("pass")
    trace = DecisionTrace("decision-1", spec, response, 1, True, "agent_timeout")

    assert trace.agent_spec == spec
    assert trace.response == response
    assert trace.fallback_used
