from datetime import UTC, datetime

from werewolf_agent.clients.streamlit.i18n import load_i18n
from werewolf_agent.clients.streamlit.icons import action_icon, event_icon
from werewolf_agent.clients.streamlit.view_models import (
    build_game_screen_view,
    game_option_label,
    target_candidates_for_action,
)
from werewolf_agent.clients.streamlit.view_models.formatting import _display_player_name
from werewolf_agent.contracts.schemas import (
    GameTimelineItem,
    PlayerObservation,
    PlayerObservationResponse,
    PublicGameState,
    PublicGameSummary,
    PublicPlayerState,
)
from werewolf_agent.settings import AppSettings


def _catalog():
    return load_i18n(AppSettings(_env_file=None))


def _state(*, status: str = "running", winner: str | None = None) -> PublicGameState:
    return PublicGameState(
        game_id="game-1",
        status=status,
        phase="finished" if status == "completed" else "day_discussion",
        day=2,
        version=3,
        players=[
            PublicPlayerState(id="player-1", name="P1", alive=True, status="alive"),
            PublicPlayerState(id="player-2", name="P2", alive=True, status="alive"),
            PublicPlayerState(id="player-3", name="P3", alive=False, status="dead"),
        ],
        alive_player_ids=["player-1", "player-2"],
        eliminated_player_ids=["player-3"],
        winner=winner,
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


def test_configured_player_name_is_not_rewritten_as_a_seat_label() -> None:
    assert _display_player_name("Player 3", fallback="p3") == "Player 3"


def test_screen_view_keeps_private_role_out_of_public_timeline() -> None:
    catalog = _catalog()
    observation = PlayerObservationResponse(
        game_id="game-1",
        player_id="player-1",
        observation={
            "phase": "day_discussion",
            "day": 2,
            "me": {
                "id": "player-1",
                "name": "P1",
                "status": "alive",
                "role": "seer",
            },
            "players": [],
            "known_roles": {"player-2": "werewolf"},
            "available_actions": [
                {
                    "key": "speech",
                    "type": "speech",
                    "legal_target_ids": [],
                    "message_required": True,
                }
            ],
        },
    )

    screen = build_game_screen_view(
        state=_state(),
        turns=[_turn("unknown_private_event", {"target_id": "player-2", "role": "werewolf"})],
        observation=observation,
        manual_player_id="player-1",
        screen_mode="playable",
        catalog=catalog,
        lang="ja",
    )

    assert screen.screen_mode == "playable"
    assert screen.observation is not None
    assert screen.observation.role == "占い師"
    timeline_text = " ".join(f"{item.title} {item.detail}" for item in screen.timeline)
    assert "werewolf" not in timeline_text
    assert "player-2" not in timeline_text
    assert screen.can_submit_action is True
    assert screen.seats[0].activity == "入力待ち"
    memo_text = " ".join(screen.observation_memo.lines)
    assert "あなたの入力待ちです。" in memo_text
    assert "werewolf" not in memo_text
    assert "player-2" not in memo_text


def test_timeline_renders_public_speech_vote_and_night_results() -> None:
    catalog = _catalog()
    turns = [
        _turn("speech_recorded", {"utterance": "根拠を聞きたいです。"}),
        _turn("vote_submitted", {"target_id": "player-2"}),
        _turn("vote_resolved", {"eliminated_player_id": "player-2", "counts": {"player-2": 2}}),
        _turn("night_resolved", {"killed_player_id": "player-3"}),
    ]

    screen = build_game_screen_view(
        state=_state(),
        turns=turns,
        observation=None,
        manual_player_id=None,
        screen_mode="observer",
        catalog=catalog,
        lang="ja",
    )

    details = [item.detail for item in screen.timeline]
    assert details[0] == "P1: 「根拠を聞きたいです。」"
    assert details[1] == "P1 が P2 に投票しました。"
    assert details[2] == "投票の結果、P2 が退場しました。"
    assert details[3] == "夜が明け、P3 が犠牲になりました。"


def test_observer_mode_uses_only_public_timeline_without_action_state() -> None:
    catalog = _catalog()
    screen = build_game_screen_view(
        state=_state(status="completed", winner="village"),
        turns=[_turn("game_finished", {"winner": "village"})],
        observation=None,
        manual_player_id=None,
        screen_mode="observer",
        catalog=catalog,
        lang="ja",
    )

    assert screen.screen_mode == "observer"
    assert screen.can_submit_action is False
    assert screen.current_turn_title == "ゲームは終了しました"
    assert screen.hand_panel.heading == "観戦モード"
    assert screen.observation is None
    assert screen.observer_log is not None
    assert screen.observer_log.entries
    assert screen.observer_log.entries[0] == "1日目 決着: 村人陣営の勝利です。"
    assert screen.result_summary is not None
    summary = " ".join(screen.result_summary.facts)
    assert "全役職" not in summary
    assert "人狼" not in summary


def test_play_result_summary_uses_public_information_only() -> None:
    catalog = _catalog()
    screen = build_game_screen_view(
        state=_state(status="completed", winner="village"),
        turns=[_turn("game_finished", {"winner": "village"})],
        observation=None,
        manual_player_id=None,
        screen_mode="playable",
        catalog=catalog,
        lang="ja",
    )

    assert screen.result_summary is not None
    summary_text = " ".join(screen.result_summary.facts)
    assert "勝利陣営" in summary_text
    assert "2日目で終了しました。" in summary_text
    assert "Day" not in summary_text
    assert "勝利の勝利" not in summary_text
    assert "全役職" not in summary_text
    assert "werewolf" not in summary_text


def test_winner_label_leaves_victory_sentence_to_each_language() -> None:
    catalog = _catalog()
    screen = build_game_screen_view(
        state=_state(status="completed", winner="village"),
        turns=[_turn("game_finished", {"winner": "village"})],
        observation=None,
        manual_player_id=None,
        screen_mode="observer",
        catalog=catalog,
        lang="en",
    )

    assert screen.result_summary is not None
    assert screen.result_summary.facts[0] == "Winner: Village Team."
    assert screen.result_summary.facts[-1] == "Last public event: Village Team won."


def test_status_metrics_use_public_game_context_without_ids() -> None:
    catalog = _catalog()
    screen = build_game_screen_view(
        state=_state(),
        turns=[],
        observation=None,
        manual_player_id=None,
        screen_mode="observer",
        catalog=catalog,
        lang="ja",
        refresh_interval_seconds=5,
    )

    text = " ".join(f"{item.label} {item.value} {item.detail}" for item in screen.status_metrics)
    assert "次の更新 5 秒" in text
    assert "最終更新 12:34:56" in text
    assert "game-1" not in text
    assert "player-1" not in text
    assert screen.observation_memo.title == "観測メモ\uff08公開情報\uff09"
    assert screen.observation_memo.updated_label == "12:34:56 更新"


def test_target_candidates_exclude_unavailable_targets() -> None:
    candidates = target_candidates_for_action(
        "vote",
        state=_state(),
        observation=PlayerObservation.model_validate(
            {
                "phase": "voting",
                "day": 1,
                "me": {
                    "id": "player-1",
                    "name": "P1",
                    "status": "alive",
                },
                "players": [],
                "available_actions": [
                    {
                        "key": "vote",
                        "type": "vote",
                        "legal_target_ids": ["player-2"],
                    }
                ],
            }
        ),
        manual_player_id="player-1",
    )

    assert candidates == ["player-2"]


def test_vote_evidence_choices_are_projected_from_server_authorized_facts() -> None:
    catalog = _catalog()
    observation = PlayerObservationResponse.model_validate(
        {
            "game_id": "game-1",
            "player_id": "player-1",
            "observation": {
                "phase": "voting",
                "day": 1,
                "me": {"id": "player-1", "name": "P1", "status": "alive"},
                "players": [
                    {"id": "player-1", "name": "P1", "status": "alive"},
                    {"id": "player-2", "name": "P2", "status": "alive"},
                ],
                "available_actions": [
                    {
                        "key": "vote",
                        "type": "vote",
                        "legal_target_ids": ["player-2"],
                        "evidence_options": [
                            {
                                "evidence_id": "speech-1",
                                "kind": "discussion",
                                "actor_id": "player-2",
                                "topic_id": "player-1",
                                "position": "support",
                            }
                        ],
                    }
                ],
                "history": {
                    "speeches": [
                        {
                            "day": 1,
                            "speech_id": "speech-1",
                            "round_id": "opening-1",
                            "round_kind": "opening",
                            "player_id": "player-2",
                            "utterance": "player-1を疑います。",
                            "topic_id": "player-1",
                            "position": "support",
                            "relation": "independent",
                        }
                    ]
                },
            },
        }
    )

    screen = build_game_screen_view(
        state=_state(),
        turns=[],
        observation=observation,
        manual_player_id="player-1",
        screen_mode="playable",
        catalog=catalog,
        lang="ja",
    )

    assert screen.observation is not None
    assert screen.observation.vote_evidence_choices["player-2"] == {
        "speech-1": "P2: player-1を疑います。"
    }


def test_unknown_icons_and_sidebar_labels_have_safe_defaults() -> None:
    catalog = _catalog()
    game = PublicGameSummary(
        game_id="game-unknown",
        status="running",
        phase="day_discussion",
        day=1,
        version=1,
        player_count=6,
        alive_count=6,
        step_count=0,
        turn_count=0,
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )

    assert event_icon("unknown_event").symbol == "•"
    assert action_icon("unknown_action").symbol == "•"
    assert catalog.label("ja", "event", "unknown_event") == "unknown_event"
    assert "進行中 / 1日目 / 6" in game_option_label(game, catalog, "ja")


def test_observation_memo_uses_public_timeline_sanitization() -> None:
    catalog = _catalog()
    screen = build_game_screen_view(
        state=_state(),
        turns=[
            _turn(
                "night_resolved",
                {
                    "attacked_player_id": "player-1",
                    "protected_player_id": "player-2",
                    "killed_player_id": "player-3",
                    "target_role": "werewolf",
                },
            )
        ],
        observation=None,
        manual_player_id=None,
        screen_mode="observer",
        catalog=catalog,
        lang="ja",
    )

    memo_text = " ".join(screen.observation_memo.lines)
    assert "直近:" in memo_text
    assert "P3" in memo_text
    assert "attacked_player_id" not in memo_text
    assert "protected_player_id" not in memo_text
    assert "werewolf" not in memo_text
