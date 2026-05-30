from werewolf_agent.interface.entrypoint.streamlit.components import (
    observation_panel_html,
    timeline_section_html,
)
from werewolf_agent.interface.entrypoint.streamlit.view_models import (
    ObservationView,
    TimelineItemView,
)


def test_timeline_section_uses_responsive_variant_and_empty_state() -> None:
    html = timeline_section_html([], variant="mobile")

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
        )
    )

    assert "村人。あなただけに見えている情報です。" in html
    assert "P1: &lt;secret&gt;" in html
    assert "<secret>" not in html
