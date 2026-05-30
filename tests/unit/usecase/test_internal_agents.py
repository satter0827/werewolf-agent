from werewolf_agent.domain.game.models import (
    GameHistory,
    Observation,
    Phase,
    Player,
    PlayerStatus,
    Role,
    SpeechRecord,
    VoteResult,
)
from werewolf_agent.usecase.internal.agents import (
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
            speeches=[SpeechRecord(day=2, player_id="p2", message="I want to hear from Alice.")],
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
