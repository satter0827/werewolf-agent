"""HTML component helpers for the Streamlit play screen."""

from __future__ import annotations

from html import escape
from textwrap import dedent

from werewolf_agent.clients.streamlit.view_models import (
    GameScreenView,
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
                    <h2>{escape(title)}</h2>
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
) -> str:
    """Return a complete timeline section for one responsive placement."""
    placement = css_token(variant)
    body_html = (
        timeline_html(items) if items else f'<div class="wa-empty-note">{escape(empty_text)}</div>'
    )
    return html(
        f"""
        <section class="wa-timeline-section wa-timeline-{placement}">
            <div class="wa-section-head">
                <div>
                    <h2>{escape(title)}</h2>
                    <p>{escape(description)}</p>
                </div>
            </div>
            {body_html}
        </section>
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
    if seat.is_manual:
        classes.append("wa-seat-manual")
    if seat.is_current:
        classes.append("wa-seat-current")
    if not seat.is_alive:
        classes.append("wa-seat-dead")
    status_class = "wa-chip" if seat.is_alive else "wa-chip wa-chip-muted"
    marker = escape(seat.name.strip()[:1].upper() or "-")
    return html(
        f"""
        <article class="{" ".join(classes)}">
            <div class="wa-seat-marker" aria-hidden="true">{marker}</div>
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
            <span aria-hidden="true"></span>{escape(item.label)}
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
                <b>{escape(item.title)}</b>
                <div>{escape(item.detail)}</div>
            </div>
        </div>
        """
    )
