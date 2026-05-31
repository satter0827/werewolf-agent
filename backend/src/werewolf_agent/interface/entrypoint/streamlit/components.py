"""HTML component helpers for the Streamlit play screen."""

from __future__ import annotations

from html import escape
from textwrap import dedent

from werewolf_agent.interface.entrypoint.streamlit.view_models import (
    GameScreenView,
    HandPanelView,
    ObservationView,
    ObserverLogView,
    PlayerSeatView,
    ResultSummaryView,
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


def game_table_html(screen: GameScreenView, *, title: str, description: str) -> str:
    """Return the game table markup."""
    seat_html = "".join(_seat_html(seat) for seat in screen.seats)
    legend_html = "".join(_legend_html(item) for item in screen.table_legend)
    return html(
        f"""
        <section class="wa-table-surface">
            <div class="wa-section-head">
                <div>
                    <h3>{escape(title)}</h3>
                    <p>{escape(description)}</p>
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


def timeline_section_html(
    items: list[TimelineItemView],
    *,
    variant: str,
    title: str,
    description: str,
    empty_text: str,
    result_summary: ResultSummaryView | None = None,
) -> str:
    """Return a complete timeline section for one responsive placement."""
    placement = css_token(variant)
    body_html = (
        timeline_html(items) if items else f'<div class="wa-empty-note">{escape(empty_text)}</div>'
    )
    summary_html = result_summary_html(result_summary) if result_summary is not None else ""
    return html(
        f"""
        <section class="wa-timeline-section wa-timeline-{placement}">
            <div class="wa-section-head">
                <div>
                    <h3>{escape(title)}</h3>
                    <p>{escape(description)}</p>
                </div>
            </div>
            {body_html}
            {summary_html}
        </section>
        """
    )


def observation_panel_html(
    observation: ObservationView,
    *,
    role_title: str,
    info_title: str,
    role_note_template: str,
    empty_text: str,
) -> str:
    """Return compact private observation markup for the right panel."""
    role_note = escape(role_note_template.format(role=observation.role))
    known_lines = "".join(f"<li>{escape(line)}</li>" for line in observation.known_role_lines)
    known_body = (
        f"<ul>{known_lines}</ul>"
        if known_lines
        else f'<div class="wa-private-empty">{escape(empty_text)}</div>'
    )
    return html(
        f"""
        <section class="wa-private-panel">
            <div class="wa-private-block">
                <h3>{escape(role_title)}</h3>
                <div class="wa-role-note">{role_note}</div>
            </div>
            <div class="wa-private-block">
                <h3>{escape(info_title)}</h3>
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
                    <h3>{escape(hand.heading)}</h3>
                </div>
            </div>
            <div class="wa-primary-note">
                <b>{escape(hand.title)}</b>
                <div>{escape(hand.detail)}</div>
            </div>
        </aside>
        """
    )


def observer_log_html(log: ObserverLogView) -> str:
    """Return observer-only role/action reveal markup."""
    role_lines = "".join(f"<li>{escape(line)}</li>" for line in log.role_lines)
    action_lines = "".join(f"<li>{escape(line)}</li>" for line in log.action_lines)
    action_body = (
        f"<ul>{action_lines}</ul>"
        if action_lines
        else f'<div class="wa-private-empty">{escape(log.empty_text)}</div>'
    )
    return html(
        f"""
        <section class="wa-private-panel wa-observer-log">
            <div class="wa-private-block">
                <h3>{escape(log.title)}</h3>
            </div>
            <div class="wa-private-block">
                <h3>{escape(log.role_title)}</h3>
                <ul>{role_lines}</ul>
            </div>
            <div class="wa-private-block">
                {action_body}
            </div>
        </section>
        """
    )


def result_summary_html(summary: ResultSummaryView | None) -> str:
    """Return completed-game summary markup."""
    if summary is None:
        return ""
    facts = "".join(f"<li>{escape(fact)}</li>" for fact in summary.facts)
    return html(
        f"""
        <section class="wa-result-summary">
            <h3>{escape(summary.title)}</h3>
            <p>{escape(summary.detail)}</p>
            <ul>{facts}</ul>
        </section>
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
    return "\n".join(line.strip() for line in dedent(markup).strip().splitlines())


def _seat_html(seat: PlayerSeatView) -> str:
    classes = ["wa-seat", f"wa-seat-activity-{css_token(seat.activity_tone)}"]
    if seat.is_human:
        classes.append("wa-seat-human")
    if seat.is_current:
        classes.append("wa-seat-current")
    if not seat.is_alive:
        classes.append("wa-seat-dead")
    status_class = "wa-chip" if seat.is_alive else "wa-chip wa-chip-muted"
    role_html = (
        f'<div class="wa-role-chip">{escape(seat.role_label)}</div>'
        if seat.role_label is not None
        else ""
    )
    faction_html = (
        f'<div class="wa-faction-note">{escape(seat.faction_label)}</div>'
        if seat.faction_label is not None
        else ""
    )
    return html(
        f"""
        <article class="{" ".join(classes)}">
            <div class="wa-seat-avatar">👤</div>
            <b>{escape(seat.name)}</b>
            {role_html}
            {faction_html}
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
