from werewolf_agent.clients.streamlit.components import (
    game_table_html,
    status_grid_html,
    timeline_section_html,
)
from werewolf_agent.clients.streamlit.view_models import (
    GameScreenView,
    HandPanelView,
    ObservationMemoView,
    PlayerSeatView,
    StatusMetricView,
    TimelineItemView,
)


def test_status_grid_escapes_values_without_decorative_icons() -> None:
    markup = status_grid_html([StatusMetricView("phase", "🌙", "状態", "<夜>", "待機", "warning")])

    assert "&lt;夜&gt;" in markup
    assert "🌙" not in markup
    assert "wa-status-warning" in markup


def test_game_table_uses_initial_marker_and_escapes_player_name() -> None:
    markup = game_table_html(_screen(), title="ゲーム卓", description="公開状態")

    assert "wa-seat-marker" in markup
    assert ">葵<" in markup
    assert "👤" not in markup
    assert "葵&lt;script&gt;" in markup


def test_timeline_section_is_one_public_surface() -> None:
    markup = timeline_section_html(
        [
            TimelineItemView(
                sequence=1,
                icon="●",
                tone="safe",
                title="朝になりました",
                detail="公開情報だけです。",
                time_text="12:00:00",
                day_label="Day 1",
            )
        ],
        variant="primary",
        title="公開タイムライン",
        description="公開情報だけです。",
        empty_text="空です。",
    )

    assert 'class="wa-timeline-section wa-timeline-primary"' in markup
    assert "朝になりました" in markup
    assert "●" not in markup


def _screen() -> GameScreenView:
    return GameScreenView(
        game_id="game-1",
        screen_mode="playable",
        status="running",
        phase="night",
        phase_label="夜",
        day_label="Day 1",
        status_label="進行中",
        alive_label="1 / 1",
        turn_label="0",
        player_label="葵",
        updated_label="12:00",
        winner_label="-",
        player_count=1,
        alive_count=1,
        status_metrics=[],
        table_legend=[],
        seats=[PlayerSeatView("p1", "葵<script>", "生存", "待機", "safe", True, True, False)],
        timeline=[],
        hand_panel=HandPanelView("手番", "待機", "待機中", "warning", "進行", "進めます", True),
        observation=None,
        observer_log=None,
        result_summary=None,
        observation_memo=ObservationMemoView("メモ", "更新", []),
        current_turn_title="待機",
        current_turn_detail="待機中",
        is_completed=False,
        can_submit_action=False,
    )
