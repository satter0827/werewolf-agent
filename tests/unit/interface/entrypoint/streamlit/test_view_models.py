from datetime import UTC, datetime

from werewolf_agent.contracts.schemas import (
    GameTimelineItem,
    PlayerObservationResponse,
    PublicGameRunSummary,
    PublicGameState,
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
        updated_at=datetime(2026, 1, 1, 12, 34, 56, tzinfo=UTC),
    )


def _turn(event_type: str, payload: dict[str, object]) -> GameTimelineItem:
    return GameTimelineItem(
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
    observation = PlayerObservationResponse(
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
        turns=[_turn("unknown_private_event", {"target_id": "player-2", "role": "werewolf"})],
        observation=observation,
        human_player_id="player-1",
        screen_mode="playable",
    )

    assert screen.screen_mode == "playable"
    assert screen.observation is not None
    assert screen.observation.role == "占い師"
    timeline_text = " ".join(f"{item.title} {item.detail}" for item in screen.timeline)
    assert "werewolf" not in timeline_text
    assert "player-2" not in timeline_text
    assert screen.can_submit_action is True
    assert screen.seats[0].activity == "入力待ち"


def test_timeline_renders_public_speech_vote_and_night_results() -> None:
    turns = [
        _turn("speech_recorded", {"message": "根拠を聞きたいです。"}),
        _turn("vote_submitted", {"target_id": "player-2"}),
        _turn("vote_resolved", {"eliminated_player_id": "player-2", "counts": {"player-2": 2}}),
        _turn("night_resolved", {"killed_player_id": "player-3"}),
    ]

    screen = build_game_screen_view(
        state=_state(),
        turns=turns,
        observation=None,
        human_player_id=None,
        screen_mode="observer",
    )

    details = [item.detail for item in screen.timeline]
    assert details[0] == "P1: 「根拠を聞きたいです。」"
    assert details[1] == "P1 が P2 に投票しました。"
    assert details[2] == "投票の結果、P2 が退場しました。"
    assert details[3] == "夜が明け、P3 が犠牲になりました。"


def test_waiting_hand_panel_can_advance_until_next_input() -> None:
    observation = PlayerObservationResponse(
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
        screen_mode="playable",
    )

    assert screen.can_submit_action is False
    assert screen.current_turn_title == "進行待ち"
    assert screen.hand_panel.title == "進行待ち"
    assert screen.hand_panel.can_advance is True


def test_observer_mode_hides_private_and_action_state() -> None:
    screen = build_game_screen_view(
        state=_state(),
        turns=[],
        observation=None,
        human_player_id=None,
        screen_mode="observer",
    )

    assert screen.screen_mode == "observer"
    assert screen.can_submit_action is False
    assert screen.current_turn_title == "観戦中"
    assert screen.hand_panel.title == "観戦モード"
    assert screen.hand_panel.can_advance is False
    assert screen.player_label == "観戦中"


def test_status_metrics_use_public_game_context_without_ids() -> None:
    screen = build_game_screen_view(
        state=_state(),
        turns=[],
        observation=None,
        human_player_id=None,
        screen_mode="observer",
        refresh_interval_seconds=5,
    )

    text = " ".join(f"{item.label} {item.value} {item.detail}" for item in screen.status_metrics)
    assert "次の更新 5 秒" in text
    assert "最終更新 12:34:56" in text
    assert "game-1" not in text
    assert "player-1" not in text


def test_default_player_names_are_shown_as_compact_seat_labels() -> None:
    state = _state().model_copy(
        update={
            "players": [
                PublicPlayerState(id="player-1", name="Player 1", alive=True, status="alive"),
                PublicPlayerState(id="player-2", name="Player 2", alive=True, status="alive"),
                PublicPlayerState(id="player-3", name="Player 3", alive=False, status="dead"),
            ]
        }
    )
    observation = PlayerObservationResponse(
        game_id="game-1",
        player_id="player-1",
        observation={
            "me": {"id": "player-1", "role": "villager"},
            "known_roles": {"player-2": "werewolf"},
            "available_actions": [],
        },
    )

    screen = build_game_screen_view(
        state=state,
        turns=[],
        observation=observation,
        human_player_id="player-1",
        screen_mode="playable",
    )

    assert screen.player_label == "P1"
    assert [seat.name for seat in screen.seats] == ["P1", "P2", "P3"]
    assert screen.observation is not None
    assert screen.observation.known_role_lines == ["P2: 人狼"]


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
        human_player_id=None,
        screen_mode="observer",
    )

    assert screen.timeline[0].detail == "勝敗が決まりました。"


def test_completed_game_hides_submit_state_even_with_available_actions() -> None:
    observation = PlayerObservationResponse(
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
        screen_mode="playable",
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
    assert game_run_option_label(run) == "進行中 / Day 1 / 6人 / 最終更新 12:00:00 / 観戦のみ"
