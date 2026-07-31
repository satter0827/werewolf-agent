"""組み込みAgentが共通Session契約を満たすことを検証する."""

from __future__ import annotations

import pytest

from werewolf_agent.agents import (
    AgentContext,
    AgentObservation,
    DecisionOption,
    DecisionRequest,
    DecisionResponse,
    FaultAgentFactory,
    HeuristicAgentFactory,
    ObservedPlayer,
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

    with pytest.raises(RuntimeError, match="expected_fault"):
        factory.create(context).decide(_request(context))
    assert factory.create(context) is not factory.create(context)
