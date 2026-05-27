import random

from werewolf_agent.domain.llm.models import (
    AgentActionType,
    AgentObservation,
    AgentPhase,
    AgentPlayerStatus,
    AgentRole,
    VisiblePlayer,
)
from werewolf_agent.domain.llm.service import choose_dummy_decision


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
    )


def test_dummy_agent_returns_role_specific_night_decisions() -> None:
    wolf_decision = choose_dummy_decision(
        "p1",
        observation(
            player_id="p1",
            role=AgentRole.WEREWOLF,
            known_roles={"p1": AgentRole.WEREWOLF},
        ),
        rng=random.Random(1),
    )
    seer_decision = choose_dummy_decision(
        "p2",
        observation(player_id="p2", role=AgentRole.SEER),
        rng=random.Random(1),
    )
    knight_decision = choose_dummy_decision(
        "p3",
        observation(player_id="p3", role=AgentRole.KNIGHT),
        rng=random.Random(1),
    )
    villager_decision = choose_dummy_decision(
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


def test_dummy_agent_is_seed_deterministic_for_same_observation() -> None:
    agent_observation = observation()

    decision_a = choose_dummy_decision("p1", agent_observation, rng=random.Random(99))
    decision_b = choose_dummy_decision("p1", agent_observation, rng=random.Random(99))

    assert decision_a == decision_b


def test_dummy_agent_day_and_vote_decisions_match_phase() -> None:
    speech = choose_dummy_decision(
        "p2",
        observation(player_id="p2", role=AgentRole.SEER, phase=AgentPhase.DAY_DISCUSSION),
        rng=random.Random(3),
    )
    vote = choose_dummy_decision(
        "p2",
        observation(player_id="p2", role=AgentRole.SEER, phase=AgentPhase.VOTING),
        rng=random.Random(3),
    )

    assert speech.type is AgentActionType.SPEECH
    assert speech.message
    assert vote.type is AgentActionType.VOTE
    assert vote.target_id != "p2"


def test_dummy_agent_passes_when_observation_is_not_for_player() -> None:
    decision = choose_dummy_decision(
        "p1",
        observation(player_id="p2", role=AgentRole.SEER),
        rng=random.Random(3),
    )

    assert decision.type is AgentActionType.PASS
    assert decision.reason == "observation belongs to another player"
