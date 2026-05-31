import pytest

from werewolf_agent.commons.shared.definitions import (
    FakeDecisionCatalog,
    PromptDefinition,
    PromptMessageDefinition,
)
from werewolf_agent.domain.llm.models import (
    AgentActionType,
    AgentObservation,
    AgentPhase,
    AgentPlayerStatus,
    VisiblePlayer,
)
from werewolf_agent.domain.llm.service import (
    LangChainDecisionProvider,
)
from werewolf_agent.interface.runtime.resources import load_llm_definitions


def players() -> list[VisiblePlayer]:
    return [
        VisiblePlayer(id="p1", name="Alice", status=AgentPlayerStatus.ALIVE),
        VisiblePlayer(id="p2", name="Bob", status=AgentPlayerStatus.ALIVE),
        VisiblePlayer(id="p3", name="Chika", status=AgentPlayerStatus.ALIVE),
        VisiblePlayer(id="p4", name="Dan", status=AgentPlayerStatus.ALIVE),
        VisiblePlayer(id="p5", name="Eve", status=AgentPlayerStatus.ALIVE),
    ]


def observation(
    *,
    player_id: str = "p1",
    role: str = "werewolf",
    phase: AgentPhase = AgentPhase.NIGHT,
    known_roles: dict[str, str] | None = None,
    available_actions: list[AgentActionType] | None = None,
) -> AgentObservation:
    visible_players = players()
    me = next(player for player in visible_players if player.id == player_id)
    return AgentObservation(
        phase=phase,
        day=1,
        me=me,
        role=role,
        players=visible_players,
        known_roles=known_roles or {},
        available_actions=available_actions
        if available_actions is not None
        else _available_actions(role, phase),
        speeches=[],
        vote_rounds=[],
    )


def _available_actions(role: str, phase: AgentPhase) -> list[AgentActionType]:
    if phase is AgentPhase.DAY_DISCUSSION:
        return [AgentActionType.SPEECH]
    if phase is AgentPhase.VOTING:
        return [AgentActionType.VOTE]
    if phase is AgentPhase.NIGHT:
        return {
            "werewolf": [AgentActionType.WEREWOLF_ATTACK],
            "seer": [AgentActionType.SEER_INSPECT],
            "knight": [AgentActionType.KNIGHT_GUARD],
            "villager": [],
        }[role]
    return []


def provider() -> LangChainDecisionProvider:
    definitions = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    )
    return LangChainDecisionProvider(
        prompt=definitions.prompt,
        fake_responses=definitions.fake_responses,
    )


def test_prompt_resource_uses_mlflow_style_metadata_and_langchain_variables() -> None:
    prompt = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    ).prompt

    assert prompt.name == "werewolf-agent-decision"
    assert prompt.alias == "local"
    assert prompt.tags["task"] == "agent_decision"
    assert prompt.model_config_metadata["model_name"] == "fake-list-llm"
    assert prompt.response_format["schema"] == "AgentDecision"
    assert "{{player_id}}" in prompt.messages[-1].content
    assert "{player_id}" in prompt.messages[-1].langchain_content()


def test_fake_response_resource_uses_action_response_pools() -> None:
    fake_responses = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    ).fake_responses

    assert fake_responses.name == "werewolf-agent-fake-decisions"
    assert fake_responses.tags["provider"] == "fake-list-llm"
    assert len(fake_responses.templates[AgentActionType.SPEECH.value]) > 1
    assert fake_responses.render(
        AgentActionType.VOTE.value,
        context={
            "player_id": "p1",
            "target_id": "p2",
            "target_name": "Bob",
        },
    ).startswith('{"type":"vote"')


def test_prompt_resource_rejects_missing_variable_metadata() -> None:
    with pytest.raises(ValueError, match="message variables missing"):
        PromptDefinition(
            name="bad",
            version=1,
            alias="local",
            input_variables=["player_id"],
            response_format={"schema": "AgentDecision"},
            messages=[
                PromptMessageDefinition(
                    role="human",
                    content="{{player_id}} {{missing}}",
                )
            ],
        )


def test_langchain_fake_provider_returns_role_specific_night_decisions() -> None:
    wolf_decision = provider().choose_decision(
        "p1",
        observation(
            player_id="p1",
            role="werewolf",
            known_roles={"p1": "werewolf"},
        ),
    )
    seer_decision = provider().choose_decision(
        "p2",
        observation(player_id="p2", role="seer"),
    )
    knight_decision = provider().choose_decision(
        "p3",
        observation(player_id="p3", role="knight"),
    )
    villager_decision = provider().choose_decision(
        "p4",
        observation(player_id="p4", role="villager"),
    )

    assert wolf_decision.type is AgentActionType.WEREWOLF_ATTACK
    assert wolf_decision.target_id != "p1"
    assert seer_decision.type is AgentActionType.SEER_INSPECT
    assert seer_decision.target_id != "p2"
    assert knight_decision.type is AgentActionType.KNIGHT_GUARD
    assert villager_decision.type is AgentActionType.PASS


def test_langchain_fake_provider_day_and_vote_decisions_match_phase() -> None:
    speech = provider().choose_decision(
        "p2",
        observation(player_id="p2", role="seer", phase=AgentPhase.DAY_DISCUSSION),
    )
    vote = provider().choose_decision(
        "p2",
        observation(player_id="p2", role="seer", phase=AgentPhase.VOTING),
    )

    assert speech.type is AgentActionType.SPEECH
    assert speech.message
    assert vote.type is AgentActionType.VOTE
    assert vote.target_id != "p2"


def test_langchain_fake_provider_passes_when_observation_is_not_for_player() -> None:
    decision = provider().choose_decision(
        "p1",
        observation(player_id="p2", role="seer"),
    )

    assert decision.type is AgentActionType.PASS
    assert decision.reason == "observation belongs to another player"


def test_langchain_fake_provider_falls_back_for_invalid_json() -> None:
    fake_responses = FakeDecisionCatalog.model_validate(
        {
            "name": "bad",
            "version": 1,
            "alias": "local",
            "templates": {
                "vote": "not json",
                "pass": '{"type":"pass","player_id":"$player_id","reason":"fallback"}',
            },
        }
    )
    definitions = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    )
    decision = LangChainDecisionProvider(
        prompt=definitions.prompt,
        fake_responses=fake_responses,
    ).choose_decision(
        "p2",
        observation(player_id="p2", role="seer", phase=AgentPhase.VOTING),
    )

    assert decision.type is AgentActionType.PASS
    assert decision.reason.startswith("invalid llm decision")


def test_langchain_fake_provider_falls_back_for_invalid_target() -> None:
    fake_responses = FakeDecisionCatalog.model_validate(
        {
            "name": "bad",
            "version": 1,
            "alias": "local",
            "templates": {
                "vote": (
                    '{"type":"vote","player_id":"$player_id",'
                    '"target_id":"missing","reason":"bad target"}'
                ),
                "pass": '{"type":"pass","player_id":"$player_id","reason":"fallback"}',
            },
        }
    )
    definitions = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    )
    decision = LangChainDecisionProvider(
        prompt=definitions.prompt,
        fake_responses=fake_responses,
    ).choose_decision(
        "p2",
        observation(player_id="p2", role="seer", phase=AgentPhase.VOTING),
    )

    assert decision.type is AgentActionType.PASS
    assert decision.reason == "llm decision target unavailable: vote"
