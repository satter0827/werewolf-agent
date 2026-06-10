from werewolf_agent.entrypoint.streamlit.components import (
    action_header_html,
    hand_panel_html,
    observation_memo_html,
    observation_panel_html,
    timeline_section_html,
)
from werewolf_agent.entrypoint.streamlit.view_models import (
    HandPanelView,
    ObservationMemoView,
    ObservationView,
    TimelineItemView,
)


def test_timeline_section_uses_responsive_variant_and_empty_state() -> None:
    html = timeline_section_html(
        [],
        variant="mobile",
        title="公開タイムライン",
        description="公開情報だけです。",
        empty_text="まだ表示できる出来事がありません。",
    )

    assert 'class="wa-timeline-section wa-timeline-mobile"' in html
    assert "まだ表示できる出来事がありません。" in html


def test_timeline_section_renders_public_rows() -> None:
    html = timeline_section_html(
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
        variant="desktop",
        title="公開タイムライン",
        description="公開情報だけです。",
        empty_text="空です。",
    )

    assert 'class="wa-timeline-section wa-timeline-desktop"' in html
    assert "朝になりました" in html
    assert "公開情報だけです。" in html


def test_observation_panel_escapes_private_lines() -> None:
    html = observation_panel_html(
        ObservationView(
            role="村人",
            available_actions=[],
            action_choices=[],
            known_role_lines=["P1: <secret>"],
            target_candidates={},
        ),
        role_title="あなたの役職",
        info_title="見えている情報",
        role_note_template="あなただけに見えている情報です。",
        empty_text="いま表示できる追加情報はありません。",
    )

    assert "wa-private-summary" in html
    assert "あなたの役職" in html
    assert "村人" in html
    assert "あなただけに見えている情報です。" in html
    assert "wa-private-visible" in html
    assert "P1: &lt;secret&gt;" in html
    assert "<secret>" not in html
    assert "wa-command-section" in html


def test_hand_panel_renders_compact_status_card() -> None:
    html = hand_panel_html(
        HandPanelView(
            heading="あなたの手番",
            title="進行待ち",
            detail="次の入力待ちまで進められます。",
            tone="day",
            advance_title="今できること",
            advance_detail="次にあなたの入力が必要な場面までゲームを進められます。",
            can_advance=True,
        )
    )

    assert 'class="wa-hand-panel wa-command-section wa-hand-panel-day"' in html
    assert "wa-hand-label" in html
    assert "あなたの手番" in html
    assert "進行待ち" in html


def test_observation_memo_escapes_public_lines() -> None:
    title = "観測メモ\uff08公開情報\uff09"
    html = observation_memo_html(
        ObservationMemoView(
            title=title,
            updated_label="12:00:00 更新",
            lines=["直近: <script>", "生存プレイヤー: 6 / 6"],
        )
    )

    assert title in html
    assert "12:00:00 更新" in html
    assert "直近: &lt;script&gt;" in html
    assert "<script>" not in html
    assert "wa-command-section" in html


def test_action_header_escapes_label_and_uses_command_class() -> None:
    html = action_header_html("あなたの<input>")

    assert "wa-action-block wa-command-section" in html
    assert "あなたの&lt;input&gt;" in html
    assert "<input>" not in html
