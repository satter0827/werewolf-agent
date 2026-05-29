from datetime import UTC, datetime

from werewolf_agent.contracts.schemas import (
    PrivateObservationResponse,
    PublicGameState,
    PublicGameTurn,
    PublicPlayerState,
)
from werewolf_agent.interface.entrypoint.streamlit.view_models import (
    build_game_screen_view,
    target_candidates_for_action,
)


def _state() -> PublicGameState:
    return PublicGameState(
        game_id="game-1",
        status="running",
        phase="day_discussion",
        day=2,
        version=3,
        seed=1,
        players=[
            PublicPlayerState(id="player-1", name="P1", alive=True, status="alive"),
            PublicPlayerState(id="player-2", name="P2", alive=True, status="alive"),
            PublicPlayerState(id="player-3", name="P3", alive=False, status="dead"),
        ],
        alive_player_ids=["player-1", "player-2"],
        eliminated_player_ids=["player-3"],
        summary={"alive_count": 2},
    )


def _turn(event_type: str, payload: dict[str, object]) -> PublicGameTurn:
    return PublicGameTurn(
        sequence=1,
        event_sequence=1,
        version=1,
        phase="night",
        day=1,
        actor_id="player-1",
        event_type=event_type,
        payload=payload,
        occurred_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )


def test_screen_view_keeps_private_role_out_of_public_timeline() -> None:
    observation = PrivateObservationResponse(
        game_id="game-1",
        player_id="player-1",
        observation={
            "me": {"id": "player-1", "role": "seer"},
            "known_roles": {"player-2": "werewolf"},
            "available_actions": ["speech"],
        },
    )

    screen = build_game_screen_view(
        state=_state(),
        turns=[_turn("night_action_recorded", {"target_id": "player-2", "role": "werewolf"})],
        observation=observation,
        human_player_id="player-1",
    )

    assert screen.observation is not None
    assert screen.observation.role == "占い師"
    timeline_text = " ".join(f"{item.title} {item.detail}" for item in screen.timeline)
    assert "werewolf" not in timeline_text
    assert "player-2" not in timeline_text


def test_target_candidates_exclude_unavailable_targets() -> None:
    candidates = target_candidates_for_action(
        "vote",
        state=_state(),
        observation={"known_roles": {}},
        human_player_id="player-1",
    )

    assert candidates == ["player-2"]


def test_finished_timeline_without_winner_uses_safe_detail() -> None:
    screen = build_game_screen_view(
        state=_state(),
        turns=[_turn("game_finished", {})],
        observation=None,
        human_player_id="player-1",
    )

    assert screen.timeline[0].detail == "勝敗が決まりました。"
