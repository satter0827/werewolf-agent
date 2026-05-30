from datetime import UTC, datetime

from werewolf_agent.contracts.schemas import (
    PrivateObservationResponse,
    PublicGameRunSummary,
    PublicGameState,
    PublicGameTurn,
    PublicPlayerState,
)
from werewolf_agent.interface.entrypoint.streamlit.icons import action_icon, event_icon
from werewolf_agent.interface.entrypoint.streamlit.view_models import (
    build_game_screen_view,
    game_run_option_label,
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
    assert screen.can_submit_action is True
    assert screen.seats[0].activity == "入力待ち"


def test_waiting_hand_panel_can_advance_until_next_input() -> None:
    observation = PrivateObservationResponse(
        game_id="game-1",
        player_id="player-1",
        observation={
            "me": {"id": "player-1", "role": "villager"},
            "available_actions": [],
        },
    )

    screen = build_game_screen_view(
        state=_state(),
        turns=[],
        observation=observation,
        human_player_id="player-1",
    )

    assert screen.can_submit_action is False
    assert screen.current_turn_title == "進行待ち"
    assert screen.hand_panel.title == "進行待ち"
    assert screen.hand_panel.can_advance is True


def test_missing_operation_key_does_not_offer_advance() -> None:
    screen = build_game_screen_view(
        state=_state(),
        turns=[],
        observation=None,
        human_player_id="player-1",
    )

    assert screen.can_submit_action is False
    assert screen.current_turn_title == "操作情報が必要"
    assert screen.hand_panel.title == "操作情報が必要です"
    assert screen.hand_panel.can_advance is False


def test_target_candidates_exclude_unavailable_targets() -> None:
    candidates = target_candidates_for_action(
        "vote",
        state=_state(),
        observation={"known_roles": {}},
        human_player_id="player-1",
    )

    assert candidates == ["player-2"]


def test_target_candidates_hide_self_and_known_werewolves_for_night_attack() -> None:
    candidates = target_candidates_for_action(
        "werewolf_attack",
        state=_state(),
        observation={"known_roles": {"player-1": "werewolf", "player-2": "werewolf"}},
        human_player_id="player-1",
    )

    assert candidates == []


def test_finished_timeline_without_winner_uses_safe_detail() -> None:
    screen = build_game_screen_view(
        state=_state(),
        turns=[_turn("game_finished", {})],
        observation=None,
        human_player_id="player-1",
    )

    assert screen.timeline[0].detail == "勝敗が決まりました。"


def test_completed_game_hides_submit_state_even_with_available_actions() -> None:
    observation = PrivateObservationResponse(
        game_id="game-1",
        player_id="player-1",
        observation={
            "me": {"id": "player-1", "role": "villager"},
            "available_actions": ["speech", "vote"],
        },
    )
    screen = build_game_screen_view(
        state=_state().model_copy(update={"status": "completed", "phase": "finished"}),
        turns=[],
        observation=observation,
        human_player_id="player-1",
    )

    assert screen.is_completed is True
    assert screen.can_submit_action is False
    assert screen.current_turn_title == "ゲームは終了しました"
    assert screen.hand_panel.title == "ゲームは終了しました"
    assert screen.hand_panel.can_advance is False


def test_unknown_icons_and_sidebar_labels_have_safe_defaults() -> None:
    run = PublicGameRunSummary(
        game_id="game-unknown",
        status="running",
        phase="day_discussion",
        day=1,
        version=1,
        seed=None,
        player_count=6,
        alive_count=6,
        step_count=0,
        turn_count=0,
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )

    assert event_icon("unknown_event").label == "出来事"
    assert action_icon("unknown_action").label == "行動"
    assert game_run_option_label(run) == "進行中 / Day 1 / game-unknown"
