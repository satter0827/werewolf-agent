import logging

import pytest

from werewolf_agent.domain.game.models import (
    Action,
    GameHistory,
    Observation,
    Phase,
    Player,
    PlayerStatus,
    Role,
    VoteResult,
)
from werewolf_agent.usecase.internal.agents import (
    FakeLlmAgentFactory,
    _agent_observation_from_game,
)


def test_agent_observation_from_game_carries_public_history_only() -> None:
    game_observation = Observation(
        phase=Phase.VOTING,
        day=2,
        me=Player(id="p1", name="Alice", role=Role.SEER),
        players=[
            Player(id="p1", name="Alice", role=Role.SEER),
            Player(id="p2", name="Bob", status=PlayerStatus.ALIVE),
        ],
        known_roles={"p1": Role.SEER},
        history=GameHistory(
            speeches=[Action.speech("p2", "I want to hear from Alice.")],
            votes=[
                VoteResult(
                    day=1,
                    votes={"p1": "p2"},
                    counts={"p2": 1},
                    eliminated_player_id=None,
                    tie_break_policy="no_elimination",
                )
            ],
        ),
    )

    agent_observation = _agent_observation_from_game(game_observation)

    assert agent_observation.speeches[0].player_id == "p2"
    assert agent_observation.speeches[0].message == "I want to hear from Alice."
    assert agent_observation.vote_rounds[0].votes == {"p1": "p2"}
    assert agent_observation.vote_rounds[0].counts == {"p2": 1}
    assert agent_observation.known_roles == {"p1": Role.SEER.value}


def test_fake_llm_debug_log_avoids_secret_decision_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    game_observation = Observation(
        phase=Phase.VOTING,
        day=2,
        me=Player(id="p1", name="Alice", role=Role.SEER),
        players=[
            Player(id="p1", name="Alice", role=Role.SEER),
            Player(id="p2", name="Bob", status=PlayerStatus.ALIVE),
        ],
        known_roles={"p1": Role.SEER},
    )
    agent = FakeLlmAgentFactory().create("p1", seed=1)

    with caplog.at_level(logging.DEBUG, logger="werewolf_agent.usecase.internal.agents"):
        agent.act(game_observation)

    record = next(
        record for record in caplog.records if record.message == "fake_llm decision selected"
    )
    assert record.actor_id == "p1"
    assert record.phase == "voting"
    assert record.day == 2
    assert record.decision_type == "vote"
    assert record.candidate_count == 1
    assert not hasattr(record, "role")
    assert not hasattr(record, "known_roles")
    assert not hasattr(record, "target_id")
    assert not hasattr(record, "message_text")
