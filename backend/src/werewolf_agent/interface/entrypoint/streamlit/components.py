"""HTML component helpers for the Streamlit play screen."""

from __future__ import annotations

from html import escape
from textwrap import dedent

from werewolf_agent.interface.entrypoint.streamlit.view_models import (
    GameScreenView,
    HandPanelView,
    ObservationView,
    PlayerSeatView,
    StatusMetricView,
    TableLegendItemView,
    TimelineItemView,
)


def status_grid_html(metrics: list[StatusMetricView]) -> str:
    """Return the top status grid markup."""
    items = []
    for metric in metrics:
        tone = css_token(metric.tone)
        items.append(
            html(
                f"""
                <div class="wa-status wa-status-{tone}">
                    <div class="wa-status-icon">{escape(metric.icon)}</div>
                    <div>
                        <div class="wa-muted">{escape(metric.label)}</div>
                        <b>{escape(metric.value)}</b>
                        <div class="wa-status-detail">{escape(metric.detail)}</div>
                    </div>
                </div>
                """
            )
        )
    return f'<div class="wa-status-grid">{"".join(items)}</div>'


def game_table_html(screen: GameScreenView) -> str:
    """Return the game table markup."""
    seat_html = "".join(_seat_html(seat) for seat in screen.seats)
    legend_html = "".join(_legend_html(item) for item in screen.table_legend)
    return html(
        f"""
        <section class="wa-table-surface">
            <div class="wa-section-head">
                <div>
                    <h3>ゲーム卓</h3>
                    <p>プレイヤーの生存状態と、いま卓で起きている動きです。</p>
                </div>
                <div class="wa-table-legend">{legend_html}</div>
            </div>
            <div class="wa-seat-grid">{seat_html}</div>
        </section>
        """
    )


def timeline_html(items: list[TimelineItemView]) -> str:
    """Return timeline rows markup."""
    rows = "".join(_timeline_row_html(item) for item in items)
    return f'<div class="wa-timeline">{rows}</div>'


def timeline_section_html(items: list[TimelineItemView], *, variant: str) -> str:
    """Return a complete timeline section for one responsive placement."""
    placement = css_token(variant)
    body_html = (
        timeline_html(items)
        if items
        else '<div class="wa-empty-note">まだ表示できる出来事がありません。</div>'
    )
    return html(
        f"""
        <section class="wa-timeline-section wa-timeline-{placement}">
            <div class="wa-section-head">
                <div>
                    <h3>公開タイムライン</h3>
                    <p>公開された出来事を時系列で表示します。(詳細は非公開です)</p>
                </div>
            </div>
            {body_html}
        </section>
        """
    )


def observation_panel_html(observation: ObservationView) -> str:
    """Return compact private observation markup for the right panel."""
    role_note = f"{escape(observation.role)}。あなただけに見えている情報です。"
    known_lines = "".join(f"<li>{escape(line)}</li>" for line in observation.known_role_lines)
    known_body = (
        f"<ul>{known_lines}</ul>"
        if known_lines
        else '<div class="wa-private-empty">いま表示できる追加情報はありません。</div>'
    )
    return html(
        f"""
        <section class="wa-private-panel">
            <div class="wa-private-block">
                <h3>あなたの役職</h3>
                <div class="wa-role-note">{role_note}</div>
            </div>
            <div class="wa-private-block">
                <h3>見えている情報</h3>
                {known_body}
            </div>
        </section>
        """
    )


def hand_panel_html(hand: HandPanelView) -> str:
    """Return the right hand-panel summary markup."""
    tone = css_token(hand.tone)
    return html(
        f"""
        <aside class="wa-hand-panel wa-hand-panel-{tone}">
            <div class="wa-section-head">
                <div>
                    <h3>あなたの手番</h3>
                </div>
            </div>
            <div class="wa-primary-note">
                <b>{escape(hand.title)}</b>
                <div>{escape(hand.detail)}</div>
            </div>
        </aside>
        """
    )


def advance_note_html(hand: HandPanelView) -> str:
    """Return the waiting-state advance guidance markup."""
    return html(
        f"""
        <div class="wa-advance-note">
            <b>{escape(hand.advance_title)}</b>
            <div>{escape(hand.advance_detail)}</div>
        </div>
        """
    )


def css_token(value: str) -> str:
    """Return a safe CSS suffix token."""
    return "".join(char for char in value.lower() if char.isalnum() or char == "-") or "neutral"


def html(markup: str) -> str:
    """Normalize indentation in inline HTML fragments."""
    return dedent(markup).strip()


def _seat_html(seat: PlayerSeatView) -> str:
    classes = ["wa-seat", f"wa-seat-activity-{css_token(seat.activity_tone)}"]
    if seat.is_human:
        classes.append("wa-seat-human")
    if seat.is_current:
        classes.append("wa-seat-current")
    if not seat.is_alive:
        classes.append("wa-seat-dead")
    status_class = "wa-chip" if seat.is_alive else "wa-chip wa-chip-muted"
    return html(
        f"""
        <article class="{" ".join(classes)}">
            <div class="wa-seat-avatar">👤</div>
            <b>{escape(seat.name)}</b>
            <div class="{status_class}">{escape(seat.status)}</div>
            <div class="wa-activity">{escape(seat.activity)}</div>
        </article>
        """
    )


def _legend_html(item: TableLegendItemView) -> str:
    return html(
        f"""
        <span class="wa-legend-item wa-legend-{css_token(item.tone)}">
            <span>{escape(item.symbol)}</span>{escape(item.label)}
        </span>
        """
    )


def _timeline_row_html(item: TimelineItemView) -> str:
    tone = css_token(item.tone)
    return html(
        f"""
        <div class="wa-timeline-row wa-timeline-row-{tone}">
            <div class="wa-timeline-day">
                <b>{escape(item.day_label)}</b>
                <span>{escape(item.time_text)}</span>
            </div>
            <div class="wa-timeline-card">
                <b>{escape(item.icon)} {escape(item.title)}</b>
                <div>{escape(item.detail)}</div>
            </div>
        </div>
        """
    )
