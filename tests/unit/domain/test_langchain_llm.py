from pathlib import Path

import pytest

from werewolf_agent.domain.llm.models import (
    AgentActionType,
    AgentObservation,
    AgentPhase,
    AgentPlayerStatus,
    AgentRole,
    VisiblePlayer,
)
from werewolf_agent.domain.llm.service import (
    FakeResponseResource,
    LangChainDecisionProvider,
    build_fake_decision_provider,
    load_fake_response_resource,
    load_prompt_resource,
)


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
    role: AgentRole = AgentRole.WEREWOLF,
    phase: AgentPhase = AgentPhase.NIGHT,
    known_roles: dict[str, AgentRole] | None = None,
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


def _available_actions(role: AgentRole, phase: AgentPhase) -> list[AgentActionType]:
    if phase is AgentPhase.DAY_DISCUSSION:
        return [AgentActionType.SPEECH]
    if phase is AgentPhase.VOTING:
        return [AgentActionType.VOTE]
    if phase is AgentPhase.NIGHT:
        return {
            AgentRole.WEREWOLF: [AgentActionType.WEREWOLF_ATTACK],
            AgentRole.SEER: [AgentActionType.SEER_INSPECT],
            AgentRole.KNIGHT: [AgentActionType.KNIGHT_GUARD],
            AgentRole.VILLAGER: [],
        }[role]
    return []


def provider() -> LangChainDecisionProvider:
    return build_fake_decision_provider()


def test_prompt_resource_uses_mlflow_style_metadata_and_langchain_variables() -> None:
    prompt = load_prompt_resource()

    assert prompt.name == "werewolf-agent-decision"
    assert prompt.alias == "local"
    assert prompt.tags["task"] == "agent_decision"
    assert prompt.model_config_metadata["model_name"] == "fake-list-llm"
    assert prompt.response_format["schema"] == "AgentDecision"
    assert "{{player_id}}" in prompt.messages[-1].content
    assert "{player_id}" in prompt.messages[-1].langchain_content()


def test_fake_response_resource_uses_action_response_pools() -> None:
    fake_responses = load_fake_response_resource()

    assert fake_responses.name == "werewolf-agent-fake-decisions"
    assert fake_responses.tags["provider"] == "fake-list-llm"
    assert len(fake_responses.responses[AgentActionType.SPEECH]) > 1
    assert fake_responses.response_for(
        AgentActionType.VOTE,
        player_id="p1",
        target_id="p2",
    ).startswith('{"type":"vote"')


def test_prompt_resource_rejects_missing_variable_metadata(tmp_path: Path) -> None:
    prompt_file = tmp_path / "bad_prompt.toml"
    prompt_file.write_text(
        """
name = "bad"
version = 1
alias = "local"
input_variables = ["player_id"]
response_format = { schema = "AgentDecision" }
[[messages]]
role = "human"
content = "{{player_id}} {{missing}}"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="message variables missing"):
        load_prompt_resource(prompt_file)


def test_langchain_fake_provider_returns_role_specific_night_decisions() -> None:
    wolf_decision = provider().choose_decision(
        "p1",
        observation(
            player_id="p1",
            role=AgentRole.WEREWOLF,
            known_roles={"p1": AgentRole.WEREWOLF},
        ),
    )
    seer_decision = provider().choose_decision(
        "p2",
        observation(player_id="p2", role=AgentRole.SEER),
    )
    knight_decision = provider().choose_decision(
        "p3",
        observation(player_id="p3", role=AgentRole.KNIGHT),
    )
    villager_decision = provider().choose_decision(
        "p4",
        observation(player_id="p4", role=AgentRole.VILLAGER),
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
        observation(player_id="p2", role=AgentRole.SEER, phase=AgentPhase.DAY_DISCUSSION),
    )
    vote = provider().choose_decision(
        "p2",
        observation(player_id="p2", role=AgentRole.SEER, phase=AgentPhase.VOTING),
    )

    assert speech.type is AgentActionType.SPEECH
    assert speech.message
    assert vote.type is AgentActionType.VOTE
    assert vote.target_id != "p2"


def test_langchain_fake_provider_passes_when_observation_is_not_for_player() -> None:
    decision = provider().choose_decision(
        "p1",
        observation(player_id="p2", role=AgentRole.SEER),
    )

    assert decision.type is AgentActionType.PASS
    assert decision.reason == "observation belongs to another player"


def test_langchain_fake_provider_falls_back_for_invalid_json() -> None:
    fake_responses = FakeResponseResource.model_validate(
        {
            "name": "bad",
            "version": 1,
            "alias": "local",
            "responses": {
                "vote": "not json",
                "pass": '{"type":"pass","player_id":"{{player_id}}","reason":"fallback"}',
            },
        }
    )
    decision = LangChainDecisionProvider(
        prompt=load_prompt_resource(),
        fake_responses=fake_responses,
    ).choose_decision(
        "p2",
        observation(player_id="p2", role=AgentRole.SEER, phase=AgentPhase.VOTING),
    )

    assert decision.type is AgentActionType.PASS
    assert decision.reason.startswith("invalid llm decision")


def test_langchain_fake_provider_falls_back_for_invalid_target() -> None:
    fake_responses = FakeResponseResource.model_validate(
        {
            "name": "bad",
            "version": 1,
            "alias": "local",
            "responses": {
                "vote": (
                    '{"type":"vote","player_id":"{{player_id}}",'
                    '"target_id":"missing","reason":"bad target"}'
                ),
                "pass": '{"type":"pass","player_id":"{{player_id}}","reason":"fallback"}',
            },
        }
    )
    decision = LangChainDecisionProvider(
        prompt=load_prompt_resource(),
        fake_responses=fake_responses,
    ).choose_decision(
        "p2",
        observation(player_id="p2", role=AgentRole.SEER, phase=AgentPhase.VOTING),
    )

    assert decision.type is AgentActionType.PASS
    assert decision.reason == "llm decision target unavailable: vote"
