import logging

from werewolf_agent.commons.configuration import AppSettings
from werewolf_agent.contracts.schemas import (
    GameResponse,
    GameTurnsResponse,
    PrivateObservationResponse,
    PublicGameState,
    PublicPlayerState,
    StepGameResponse,
)
from werewolf_agent.interface.entrypoint.streamlit import operations


class FakeStreamlitClient:
    def __init__(self) -> None:
        self.stepped = False

    def get_game(self, game_id: str) -> GameResponse:
        phase = "finished" if self.stepped else "day_discussion"
        status = "completed" if self.stepped else "running"
        return GameResponse(game_id=game_id, state=_state(status=status, phase=phase))

    def list_turns(self, game_id: str, *, after: int = 0, limit: int = 100) -> GameTurnsResponse:
        _ = after, limit
        return GameTurnsResponse(game_id=game_id, turns=[], next_after=0)

    def get_private_observation(
        self,
        game_id: str,
        player_id: str,
        *,
        control_token: str,
    ) -> PrivateObservationResponse:
        _ = control_token
        return PrivateObservationResponse(
            game_id=game_id,
            player_id=player_id,
            observation={
                "me": {"id": player_id, "role": "villager"},
                "known_roles": {},
                "available_actions": [],
            },
        )

    def step_game(self, game_id: str) -> StepGameResponse:
        self.stepped = True
        return StepGameResponse(
            game_id=game_id,
            status="completed",
            state=_state(status="completed", phase="finished"),
            events=[],
        )


def test_advance_until_input_logs_iteration_and_stop_reason(
    monkeypatch,
    caplog,
) -> None:
    client = FakeStreamlitClient()
    monkeypatch.setattr(operations, "build_streamlit_client", lambda *_args, **_kwargs: client)
    settings = AppSettings(_env_file=None, streamlit_max_auto_steps=3)

    with caplog.at_level(logging.DEBUG, logger=operations.__name__):
        result = operations.advance_until_input(
            api_url="http://api.test/api/v1",
            settings=settings,
            game_id="game-1",
            human_player_id="player-1",
            control_token="secret",
        )

    assert result.completed is True
    actions = [record.event_action for record in caplog.records]
    assert "streamlit.advance_until_input.iteration" in actions
    stopped = next(
        record
        for record in caplog.records
        if record.event_action == "streamlit.advance_until_input.stopped"
    )
    assert stopped.ui_stop_reason == "completed"
    assert not hasattr(stopped, "control_token")


def _state(*, status: str, phase: str) -> PublicGameState:
    return PublicGameState(
        game_id="game-1",
        status=status,
        phase=phase,
        day=1,
        version=2,
        seed=1,
        players=[
            PublicPlayerState(id="player-1", name="Player 1", alive=True, status="alive"),
            PublicPlayerState(id="player-2", name="Player 2", alive=True, status="alive"),
        ],
        alive_player_ids=["player-1", "player-2"],
        eliminated_player_ids=[],
        winner=None,
        summary={"alive_count": 2},
    )
