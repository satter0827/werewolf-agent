import random

import pytest

from werewolf_agent.domain.llm.models import (
    AgentActionType,
    AgentObservation,
    AgentPhase,
    AgentPlayerStatus,
    AgentRole,
    FakeLlmConfig,
    VisiblePlayer,
)
from werewolf_agent.domain.llm.service import choose_decision


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
    speeches: list[dict[str, object]] | None = None,
    vote_rounds: list[dict[str, object]] | None = None,
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
        available_actions=[],
        speeches=speeches or [],
        vote_rounds=vote_rounds or [],
    )


def choose(
    player_id: str,
    agent_observation: AgentObservation,
    *,
    rng: random.Random,
    config: FakeLlmConfig | None = None,
):
    return choose_decision(
        player_id,
        agent_observation,
        config=config or FakeLlmConfig(),
        rng=rng,
    )


def test_fake_llm_returns_role_specific_night_decisions() -> None:
    wolf_decision = choose(
        "p1",
        observation(
            player_id="p1",
            role=AgentRole.WEREWOLF,
            known_roles={"p1": AgentRole.WEREWOLF},
        ),
        rng=random.Random(1),
    )
    seer_decision = choose(
        "p2",
        observation(player_id="p2", role=AgentRole.SEER),
        rng=random.Random(1),
    )
    knight_decision = choose(
        "p3",
        observation(player_id="p3", role=AgentRole.KNIGHT),
        rng=random.Random(1),
    )
    villager_decision = choose(
        "p4",
        observation(player_id="p4", role=AgentRole.VILLAGER),
        rng=random.Random(1),
    )

    assert wolf_decision.type is AgentActionType.WEREWOLF_ATTACK
    assert wolf_decision.target_id != "p1"
    assert seer_decision.type is AgentActionType.SEER_INSPECT
    assert seer_decision.target_id != "p2"
    assert knight_decision.type is AgentActionType.KNIGHT_GUARD
    assert villager_decision.type is AgentActionType.PASS


def test_fake_llm_is_seed_deterministic_for_same_observation() -> None:
    agent_observation = observation()

    decision_a = choose("p1", agent_observation, rng=random.Random(99))
    decision_b = choose("p1", agent_observation, rng=random.Random(99))

    assert decision_a == decision_b


def test_fake_llm_day_and_vote_decisions_match_phase() -> None:
    speech = choose(
        "p2",
        observation(player_id="p2", role=AgentRole.SEER, phase=AgentPhase.DAY_DISCUSSION),
        rng=random.Random(3),
    )
    vote = choose(
        "p2",
        observation(player_id="p2", role=AgentRole.SEER, phase=AgentPhase.VOTING),
        rng=random.Random(3),
    )

    assert speech.type is AgentActionType.SPEECH
    assert speech.message
    assert vote.type is AgentActionType.VOTE
    assert vote.target_id != "p2"


def test_fake_llm_passes_when_observation_is_not_for_player() -> None:
    decision = choose(
        "p1",
        observation(player_id="p2", role=AgentRole.SEER),
        rng=random.Random(3),
    )

    assert decision.type is AgentActionType.PASS
    assert decision.reason == "observation belongs to another player"


def test_fake_llm_uses_public_history_for_speech_and_vote() -> None:
    agent_observation = observation(
        player_id="p2",
        role=AgentRole.SEER,
        phase=AgentPhase.VOTING,
        speeches=[{"player_id": "p3", "message": "I suspect Alice."}],
        vote_rounds=[
            {
                "day": 1,
                "votes": {"p1": "p3", "p4": "p3", "p5": "p2"},
                "counts": {"p3": 2, "p2": 1},
            }
        ],
    )

    vote = choose(
        "p2",
        agent_observation,
        rng=random.Random(2),
        config=FakeLlmConfig(randomness=0.0),
    )

    assert vote.type is AgentActionType.VOTE
    assert vote.target_id == "p3"
    assert "fake_llm" in vote.reason


def test_fake_llm_random_strategy_can_surface_different_choices() -> None:
    agent_observation = observation(player_id="p2", role=AgentRole.SEER)
    config = FakeLlmConfig(strategy="random", randomness=1.0)

    decisions = {
        choose("p2", agent_observation, rng=random.Random(seed), config=config).target_id
        for seed in range(20)
    }

    assert len(decisions) > 1


@pytest.mark.parametrize(
    "config_kwargs",
    [
        {"strategy": "scripted"},
        {"randomness": -0.1},
        {"persona_profiles": ()},
        {"speech_intents": ("",)},
        {"speech_templates": ()},
        {"reason_templates": ()},
    ],
)
def test_fake_llm_config_rejects_invalid_values(config_kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        FakeLlmConfig(**config_kwargs)
