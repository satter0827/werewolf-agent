from datetime import UTC, datetime

from werewolf_agent.configuration import AppSettings
from werewolf_agent.contracts.schemas import (
    GameRevealPlayer,
    GameRevealResponse,
    GameTimelineItem,
    LocalRulesSettings,
    PlayerObservationResponse,
    PublicGameState,
    PublicGameSummary,
    PublicPlayerState,
)
from werewolf_agent.interfaces.streamlit.i18n import load_i18n
from werewolf_agent.interfaces.streamlit.icons import action_icon, event_icon
from werewolf_agent.interfaces.streamlit.view_models import (
    build_game_screen_view,
    game_option_label,
    target_candidates_for_action,
)


def _catalog():
    return load_i18n(AppSettings(_env_file=None))


def _state(*, status: str = "running", winner: str | None = None) -> PublicGameState:
    return PublicGameState(
        game_id="game-1",
        status=status,
        phase="finished" if status == "completed" else "day_discussion",
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


def _rules() -> LocalRulesSettings:
    return LocalRulesSettings(
        day_speech_limit_per_player=1,
        allow_self_vote=False,
        allow_vote_revision=False,
        allow_night_action_revision=False,
        enable_first_night_attack=True,
        enable_no_elimination_on_tie=True,
        enable_random_elimination_on_tie=False,
        allow_knight_self_guard=True,
        allow_knight_repeat_guard=True,
        allow_seer_self_inspect=False,
        allow_werewolf_friendly_fire=False,
        reveal_role_on_death=False,
    )


def _reveal() -> GameRevealResponse:
    return GameRevealResponse(
        game_id="game-1",
        status="completed",
        phase="finished",
        day=2,
        version=3,
        seed=1,
        role_counts={"werewolf": 1, "seer": 1, "villager": 1},
        rules=_rules(),
        players=[
            GameRevealPlayer(
                id="player-1",
                name="P1",
                role="seer",
                faction="village",
                alive=True,
                status="alive",
            ),
            GameRevealPlayer(
                id="player-2",
                name="P2",
                role="werewolf",
                faction="werewolf",
                alive=True,
                status="alive",
            ),
            GameRevealPlayer(
                id="player-3",
                name="P3",
                role="villager",
                faction="village",
                alive=False,
                status="dead",
            ),
        ],
        alive_player_ids=["player-1", "player-2"],
        eliminated_player_ids=["player-3"],
        winner="villagers",
        pending_votes=[],
        pending_night_actions=[],
        votes=[
            {
                "day": 2,
                "votes": {"player-1": "player-2"},
                "counts": {"player-2": 1},
                "eliminated_player_id": "player-2",
                "tie_break_policy": "none",
            }
        ],
        nights=[
            {
                "day": 1,
                "attacked_player_id": "player-3",
                "protected_player_id": "player-1",
                "killed_player_id": "player-3",
                "inspections": [],
            }
        ],
    )


def test_screen_view_keeps_private_role_out_of_public_timeline() -> None:
    catalog = _catalog()
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
        reveal=None,
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
        _turn("speech_recorded", {"message": "根拠を聞きたいです。"}),
        _turn("vote_submitted", {"target_id": "player-2"}),
        _turn("vote_resolved", {"eliminated_player_id": "player-2", "counts": {"player-2": 2}}),
        _turn("night_resolved", {"killed_player_id": "player-3"}),
    ]

    screen = build_game_screen_view(
        state=_state(),
        turns=turns,
        observation=None,
        reveal=None,
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


def test_observer_mode_uses_reveal_without_action_state() -> None:
    catalog = _catalog()
    screen = build_game_screen_view(
        state=_state(status="completed", winner="villagers"),
        turns=[_turn("game_finished", {"winner": "villagers"})],
        observation=None,
        reveal=_reveal(),
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
    assert "P2: 人狼 / 人狼陣営" in screen.observer_log.role_lines
    assert screen.seats[1].role_label == "人狼"
    assert screen.result_summary is not None
    assert any("全役職" in fact for fact in screen.result_summary.facts)


def test_play_result_summary_uses_public_information_only() -> None:
    catalog = _catalog()
    screen = build_game_screen_view(
        state=_state(status="completed", winner="villagers"),
        turns=[_turn("game_finished", {"winner": "villagers"})],
        observation=None,
        reveal=None,
        manual_player_id=None,
        screen_mode="playable",
        catalog=catalog,
        lang="ja",
    )

    assert screen.result_summary is not None
    summary_text = " ".join(screen.result_summary.facts)
    assert "勝利陣営" in summary_text
    assert "全役職" not in summary_text
    assert "werewolf" not in summary_text


def test_status_metrics_use_public_game_context_without_ids() -> None:
    catalog = _catalog()
    screen = build_game_screen_view(
        state=_state(),
        turns=[],
        observation=None,
        reveal=None,
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
        observation={"legal_targets": {"vote": ["player-2"]}},
        manual_player_id="player-1",
    )

    assert candidates == ["player-2"]


def test_unknown_icons_and_sidebar_labels_have_safe_defaults() -> None:
    catalog = _catalog()
    game = PublicGameSummary(
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

    assert event_icon("unknown_event").symbol == "•"
    assert action_icon("unknown_action").symbol == "•"
    assert catalog.label("ja", "event", "unknown_event") == "unknown_event"
    assert "進行中 / Day 1 / 6" in game_option_label(game, catalog, "ja")


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
        reveal=None,
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
