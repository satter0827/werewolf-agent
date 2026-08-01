"""組み込みAgentが共通Session契約を満たすことを検証する."""

from __future__ import annotations

import pytest

from werewolf_agent.agents import (
    AgentContext,
    AgentDecisionError,
    AgentFactory,
    AgentObservation,
    DecisionOption,
    DecisionRequest,
    DecisionResponse,
    EvidenceOption,
    FaultAgentFactory,
    HeuristicAgentFactory,
    ObservedPlayer,
    PublicTimelineEvent,
    RandomLegalAgentFactory,
    ScriptedAgentFactory,
)


def _request(context: AgentContext, *, seed: int = 17) -> DecisionRequest:
    me = ObservedPlayer(context.player_id, "Alice", True)
    other = ObservedPlayer("p2", "Bob", True)
    return DecisionRequest(
        "decision",
        context,
        AgentObservation("voting", 1, me, (me, other)),
        (),
        (
            DecisionOption("pass"),
            DecisionOption("vote", legal_target_ids=("p2",)),
        ),
        seed,
    )


def test_random_legal_agent_is_reproducible_for_a_decision_seed() -> None:
    context = AgentContext("session", "game", "p1", 1)
    factory = RandomLegalAgentFactory()

    first = factory.create(context).decide(_request(context))
    second = factory.create(context).decide(_request(context))

    assert first == second
    assert factory.spec.fingerprint == RandomLegalAgentFactory().spec.fingerprint


def test_heuristic_agent_uses_stable_priority_and_legal_target() -> None:
    context = AgentContext("session", "game", "p1", 1)

    response = HeuristicAgentFactory().create(context).decide(_request(context))

    assert response.action_type == "vote"
    assert response.target_id == "p2"


@pytest.mark.parametrize("factory", (RandomLegalAgentFactory(), HeuristicAgentFactory()))
def test_builtin_vote_reason_respects_authorized_limit(factory: AgentFactory) -> None:
    context = AgentContext("session", "game", "p1", 1)
    request = _request(context)
    request = DecisionRequest(
        request.decision_id,
        request.context,
        request.observation,
        request.public_timeline,
        (DecisionOption("vote", legal_target_ids=("p2",), reason_max_chars=4),),
        request.decision_seed,
    )

    response = factory.create(context).decide(request)

    assert response.reason is not None
    assert len(response.reason) <= 4


@pytest.mark.parametrize("factory", (RandomLegalAgentFactory(), HeuristicAgentFactory()))
def test_builtin_agent_response_contributes_new_content(
    factory: RandomLegalAgentFactory | HeuristicAgentFactory,
) -> None:
    """参照元と同じ定型文を応答として再送しない。"""
    context = AgentContext("session", "game", "p1", 1)
    me = ObservedPlayer("p1", "Alice", True)
    other = ObservedPlayer("p2", "Bob", True)
    request = DecisionRequest(
        "decision",
        context,
        AgentObservation("day_discussion", 1, me, (me, other)),
        (
            PublicTimelineEvent(
                1,
                "speech",
                1,
                "p2",
                {
                    "speech_id": "speech-1",
                    "utterance": factory.speech,
                    "topic_id": "p2",
                    "position": "support",
                    "relation": "independent",
                },
            ),
        ),
        (
            DecisionOption(
                "speech",
                legal_topic_ids=("p2",),
                evidence_options=(EvidenceOption("speech-1", "discussion", "p2", "p2", "support"),),
                legal_reference_ids=("speech-1",),
                legal_positions=("support", "oppose", "undecided"),
                legal_relations=("answer", "support", "challenge", "revise"),
                message_max_chars=120,
            ),
        ),
        17,
    )

    response = factory.create(context).decide(request)

    assert response.utterance != factory.speech
    assert response.response_to_id == "speech-1"


@pytest.mark.parametrize("factory", (RandomLegalAgentFactory(), HeuristicAgentFactory()))
def test_builtin_agent_honors_support_only_response_protocol(
    factory: RandomLegalAgentFactory | HeuristicAgentFactory,
) -> None:
    """組み込みAgentはsetupで許可されたsupportだけを返す."""
    context = AgentContext("session", "game", "p1", 1)
    me = ObservedPlayer("p1", "Alice", True)
    other = ObservedPlayer("p2", "Bob", True)
    request = DecisionRequest(
        "decision",
        context,
        AgentObservation("day_discussion", 1, me, (me, other)),
        (
            PublicTimelineEvent(
                1,
                "speech",
                1,
                "p2",
                {
                    "speech_id": "speech-1",
                    "utterance": "判断を保留します。",
                    "topic_id": "p2",
                    "position": "undecided",
                    "relation": "independent",
                },
            ),
        ),
        (
            DecisionOption(
                "speech",
                legal_topic_ids=("p2",),
                evidence_options=(
                    EvidenceOption("speech-1", "discussion", "p2", "p2", "undecided"),
                ),
                legal_reference_ids=("speech-1",),
                legal_positions=("support", "oppose", "undecided"),
                legal_relations=("support",),
            ),
        ),
        17,
    )

    response = factory.create(context).decide(request)

    assert response.relation == "support"
    assert response.position == "undecided"


def test_scripted_agent_state_is_isolated_by_session_and_close_is_idempotent() -> None:
    context = AgentContext("session", "game", "p1", 1)
    factory = ScriptedAgentFactory(
        (DecisionResponse("pass"), DecisionResponse("vote", target_id="p2"))
    )
    first = factory.create(context)
    second = factory.create(context)

    assert first.decide(_request(context)).action_type == "pass"
    assert first.decide(_request(context)).action_type == "vote"
    assert second.decide(_request(context)).action_type == "pass"
    first.close()
    first.close()
    with pytest.raises(RuntimeError, match="closed"):
        first.decide(_request(context))


def test_fault_agent_fails_without_affecting_other_sessions() -> None:
    context = AgentContext("session", "game", "p1", 1)
    factory = FaultAgentFactory("expected_fault")

    with pytest.raises(AgentDecisionError, match="expected_fault") as captured:
        factory.create(context).decide(_request(context))
    assert captured.value.code == "expected_fault"
    assert factory.create(context) is not factory.create(context)


@pytest.mark.parametrize(
    "factory",
    (
        RandomLegalAgentFactory(),
        HeuristicAgentFactory(),
        ScriptedAgentFactory((DecisionResponse("pass"),)),
        FaultAgentFactory(),
    ),
)
def test_builtin_factories_share_the_public_session_lifecycle(factory: AgentFactory) -> None:
    """全組み込み実装へ同じFactory、状態分離、close契約を適用する."""
    context = AgentContext("session", "game", "p1", 1)
    first = factory.create(context)
    second = factory.create(context)

    assert isinstance(factory, AgentFactory)
    assert first is not second
    first.close()
    first.close()
    with pytest.raises(RuntimeError, match="closed"):
        first.decide(_request(context))


@pytest.mark.parametrize(
    ("factory_type", "value"),
    (
        (RandomLegalAgentFactory, " "),
        (HeuristicAgentFactory, "\t"),
        (FaultAgentFactory, ""),
    ),
)
def test_builtin_factory_rejects_blank_configuration(
    factory_type: type[RandomLegalAgentFactory]
    | type[HeuristicAgentFactory]
    | type[FaultAgentFactory],
    value: str,
) -> None:
    """実行時まで遅延せずFactory構築時に空設定を拒否する."""
    with pytest.raises(ValueError, match="must not be blank"):
        factory_type(value)


def test_scripted_agent_fingerprint_accepts_nested_immutable_metadata() -> None:
    """Responseのimmutableなnested値を正規JSONへ戻してfingerprint化する."""
    response = DecisionResponse("pass", metadata={"nested": {"items": [1, 2]}})

    first = ScriptedAgentFactory((response,)).spec
    second = ScriptedAgentFactory((response,)).spec

    assert first == second
    assert first.parameters["responses"]
