"""公開Agent SDKをLLM pipelineへ接続するadapterの検証."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from werewolf_agent.adapters.llm.agent import LangChainAgentFactory
from werewolf_agent.adapters.llm.langchain.service import LangChainDecisionProvider
from werewolf_agent.adapters.llm.model_adapters import LangChainChatDecisionModel
from werewolf_agent.adapters.llm.models import DeliberationLevel, PlayerProfile
from werewolf_agent.adapters.resources import load_llm_definitions
from werewolf_agent.agents import (
    AgentAbility,
    AgentContext,
    AgentDecisionError,
    AgentIdentity,
    AgentObservation,
    AgentSession,
    AgentWorld,
    DecisionOption,
    DecisionRequest,
    ObservedPlayer,
    PublicTimelineEvent,
)


def test_langchain_factory_exposes_one_session_contract_for_chat_adapter() -> None:
    factory = _factory('{"type":"vote","target_id":"p2","reason":"公開発言から判断"}')
    context = AgentContext("session-1", "game-1", "p1", 11)
    session = factory.create(context)

    response = session.decide(_request(context))

    assert isinstance(session, AgentSession)
    assert response.action_type == "vote"
    assert response.target_id == "p2"
    assert response.metadata == {"reason": "公開発言から判断"}
    assert factory.spec.parameters["provider"] == "openai-compatible"
    assert factory.spec.parameters["base_url"] == "http://localhost:1234/v1"
    assert str(factory.spec.parameters["decision_model_type"]).endswith(
        ".LangChainChatDecisionModel"
    )
    assert len(factory.spec.fingerprint) == 64
    assert "credential" not in repr(factory.spec.parameters).lower()


def test_langchain_sessions_are_isolated_and_close_is_idempotent() -> None:
    factory = _factory('{"type":"vote","target_id":"p2","reason":"test"}')
    first_context = AgentContext("session-1", "game-1", "p1", 11)
    second_context = AgentContext("session-2", "game-1", "p1", 12)
    first = factory.create(first_context)
    second = factory.create(second_context)

    first.close()
    first.close()

    with pytest.raises(RuntimeError, match="closed"):
        first.decide(_request(first_context))
    assert second.decide(_request(second_context)).target_id == "p2"


def test_langchain_session_rejects_hidden_fallback_as_agent_error() -> None:
    factory = _factory("not-json")
    context = AgentContext("session-1", "game-1", "p1", 11)

    with pytest.raises(AgentDecisionError) as captured:
        factory.create(context).decide(_request(context))

    assert captured.value.code == "llm_decision_failed"
    assert captured.value.diagnostics["validation_status"] == "fallback"


def test_langchain_session_rejects_request_for_another_context() -> None:
    factory = _factory('{"type":"vote","target_id":"p2","reason":"test"}')
    context = AgentContext("session-1", "game-1", "p1", 11)
    other = AgentContext("session-2", "game-1", "p1", 11)

    with pytest.raises(ValueError, match="does not belong"):
        factory.create(context).decide(_request(other))


def test_langchain_session_rejects_preflight_response_outside_options() -> None:
    factory = _factory('{"type":"vote","target_id":"p2","reason":"test"}')
    context = AgentContext("session-1", "game-1", "p1", 11)
    request = _request(context)
    dead_me = ObservedPlayer("p1", "Alice", False)
    request = replace(
        request,
        observation=replace(
            request.observation,
            me=dead_me,
            players=(dead_me, request.observation.players[1]),
        ),
    )

    with pytest.raises(AgentDecisionError) as captured:
        factory.create(context).decide(request)

    assert captured.value.code == "llm_action_not_available"


def _factory(response: str) -> LangChainAgentFactory:
    definitions = load_llm_definitions(prompt_path=None, fake_responses_path=None)
    model = LangChainChatDecisionModel(
        model=FakeListChatModel(responses=[response]),
        provider_name="openai-compatible",
        model_name="fixture-model",
        base_url="http://localhost:1234/v1",
    )
    provider = LangChainDecisionProvider(
        prompt=definitions.prompt,
        decision_model=model,
        provider_name="openai-compatible",
        model_name="fixture-model",
        max_output_tokens=256,
        deliberation_level=DeliberationLevel.STANDARD,
    )
    return LangChainAgentFactory(
        provider=provider,
        profile=PlayerProfile(
            name="Analyst",
            age=30,
            gender="unspecified",
            personality="calm",
            speaking_style="concise",
            reasoning_style="evidence-first",
            risk_tolerance="medium",
        ),
    )


def _request(context: AgentContext) -> DecisionRequest:
    me = ObservedPlayer("p1", "Alice", True)
    other = ObservedPlayer("p2", "Bob", True)
    checksum = "1" * 64
    return DecisionRequest(
        decision_id=f"decision-{context.session_id}",
        context=context,
        observation=AgentObservation(
            phase="voting",
            day=1,
            me=me,
            players=(me, other),
            known_roles={"p1": "villager"},
            known_factions={"p1": "village"},
            identity=AgentIdentity(
                role_id="villager",
                role_name="村人",
                identity_faction_id="village",
                identity_faction_name="村人陣営",
                victory_team_id="village",
                victory_team_name="村人陣営",
                objective="人狼を見つける",
                abilities=(AgentAbility("discuss", "議論", "speech"),),
            ),
            world=AgentWorld(
                theme_id="standard",
                theme_name="標準村",
                premise="村に人狼が潜んでいる",
                setup_checksum=checksum,
                mechanics_checksum=checksum,
                relevant_rules={"revote": False},
                action_names={"vote": "投票"},
                phase_names={"voting": "投票"},
            ),
        ),
        public_timeline=(
            PublicTimelineEvent(
                sequence=1,
                event_type="speech",
                day=1,
                actor_id="p2",
                payload={"message": "Aliceの主張を確認したい"},
            ),
        ),
        options=(DecisionOption("vote", legal_target_ids=("p2",)),),
        decision_seed=17,
        deadline_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
