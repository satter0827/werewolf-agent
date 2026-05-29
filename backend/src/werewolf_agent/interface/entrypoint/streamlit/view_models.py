"""Pure view models for the Streamlit observer console."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from werewolf_agent.contracts.schemas import (
    PublicGameEvent,
    PublicGameState,
    PublicGameTurn,
)

TimelineSource = Literal["turn", "event"]


@dataclass(frozen=True)
class PhaseStyle:
    """Visual tone for one public game phase."""

    tone: str
    accent: str
    border: str
    background: str
    label_key: str


@dataclass(frozen=True)
class TimelineItem:
    """One observer-facing public timeline item."""

    source: TimelineSource
    sequence: int
    event_sequence: int
    version: int | None
    event_type: str
    phase: str
    day: int | None
    actor_id: str | None
    occurred_at: datetime
    payload: dict[str, Any]
    style: PhaseStyle
    headline_key: str
    summary_key: str


@dataclass(frozen=True)
class ObserverHint:
    """Current viewing hint for the side panel."""

    title_key: str
    body_key: str
    bullet_keys: tuple[str, ...]
    next_key: str


@dataclass(frozen=True)
class PlayerStatusRow:
    """Compact player state row for the side panel."""

    player_id: str
    name: str
    alive: bool
    status_key: str
    relation_key: str | None
    updated_at: datetime | None


_PHASE_STYLES: dict[str, PhaseStyle] = {
    "night": PhaseStyle(
        tone="danger",
        accent="#dc2626",
        border="#fecaca",
        background="#fff1f2",
        label_key="phase_night",
    ),
    "day_discussion": PhaseStyle(
        tone="warm",
        accent="#f59e0b",
        border="#fed7aa",
        background="#fff7ed",
        label_key="phase_day_discussion",
    ),
    "voting": PhaseStyle(
        tone="green",
        accent="#0f766e",
        border="#99f6e4",
        background="#f0fdfa",
        label_key="phase_voting",
    ),
    "finished": PhaseStyle(
        tone="neutral",
        accent="#64748b",
        border="#cbd5e1",
        background="#f8fafc",
        label_key="phase_finished",
    ),
}


_EVENT_HEADLINES: dict[str, str] = {
    "game_started": "timeline_headline_game_started",
    "phase_started": "timeline_headline_phase_started",
    "player_spoke": "timeline_headline_player_spoke",
    "vote_cast": "timeline_headline_vote_cast",
    "player_eliminated": "timeline_headline_player_eliminated",
    "night_action_resolved": "timeline_headline_night_action",
    "game_finished": "timeline_headline_game_finished",
}

_EVENT_SUMMARIES: dict[str, str] = {
    "game_started": "timeline_summary_game_started",
    "phase_started": "timeline_summary_phase_started",
    "player_spoke": "timeline_summary_player_spoke",
    "vote_cast": "timeline_summary_vote_cast",
    "player_eliminated": "timeline_summary_player_eliminated",
    "night_action_resolved": "timeline_summary_night_action",
    "game_finished": "timeline_summary_game_finished",
}


def resolve_phase_style(phase: str | None) -> PhaseStyle:
    """Return the Streamlit visual tone for a public phase value."""
    if phase is None:
        return PhaseStyle(
            tone="neutral",
            accent="#64748b",
            border="#cbd5e1",
            background="#f8fafc",
            label_key="phase_unknown",
        )
    return _PHASE_STYLES.get(
        phase,
        PhaseStyle(
            tone="neutral",
            accent="#64748b",
            border="#cbd5e1",
            background="#f8fafc",
            label_key="phase_unknown",
        ),
    )


def build_timeline_items_from_turns(turns: list[PublicGameTurn]) -> list[TimelineItem]:
    """Build observer timeline items from public turn history."""
    return [
        TimelineItem(
            source="turn",
            sequence=turn.sequence,
            event_sequence=turn.event_sequence,
            version=turn.version,
            event_type=turn.event_type,
            phase=turn.phase or "unknown",
            day=turn.day,
            actor_id=turn.actor_id,
            occurred_at=turn.occurred_at,
            payload=turn.payload,
            style=resolve_phase_style(turn.phase),
            headline_key=_EVENT_HEADLINES.get(turn.event_type, "timeline_headline_generic"),
            summary_key=_EVENT_SUMMARIES.get(turn.event_type, "timeline_summary_generic"),
        )
        for turn in turns
    ]


def build_timeline_items_from_events(events: list[PublicGameEvent]) -> list[TimelineItem]:
    """Build fallback observer timeline items from public events."""
    return [
        TimelineItem(
            source="event",
            sequence=event.sequence,
            event_sequence=event.sequence,
            version=None,
            event_type=event.event_type,
            phase=event.phase or "unknown",
            day=event.day,
            actor_id=event.actor_id,
            occurred_at=event.occurred_at,
            payload=event.payload,
            style=resolve_phase_style(event.phase),
            headline_key=_EVENT_HEADLINES.get(event.event_type, "timeline_headline_generic"),
            summary_key=_EVENT_SUMMARIES.get(event.event_type, "timeline_summary_generic"),
        )
        for event in events
    ]


def build_observer_hint(state: PublicGameState) -> ObserverHint:
    """Build phase-specific observer guidance."""
    match state.phase:
        case "night":
            return ObserverHint(
                title_key="observer_hint_night_title",
                body_key="observer_hint_night_body",
                bullet_keys=(
                    "observer_hint_night_bullet_1",
                    "observer_hint_night_bullet_2",
                    "observer_hint_night_bullet_3",
                ),
                next_key="observer_hint_night_next",
            )
        case "voting":
            return ObserverHint(
                title_key="observer_hint_voting_title",
                body_key="observer_hint_voting_body",
                bullet_keys=(
                    "observer_hint_voting_bullet_1",
                    "observer_hint_voting_bullet_2",
                    "observer_hint_voting_bullet_3",
                ),
                next_key="observer_hint_voting_next",
            )
        case "finished":
            return ObserverHint(
                title_key="observer_hint_finished_title",
                body_key="observer_hint_finished_body",
                bullet_keys=(
                    "observer_hint_finished_bullet_1",
                    "observer_hint_finished_bullet_2",
                    "observer_hint_finished_bullet_3",
                ),
                next_key="observer_hint_finished_next",
            )
        case _:
            return ObserverHint(
                title_key="observer_hint_day_title",
                body_key="observer_hint_day_body",
                bullet_keys=(
                    "observer_hint_day_bullet_1",
                    "observer_hint_day_bullet_2",
                    "observer_hint_day_bullet_3",
                ),
                next_key="observer_hint_day_next",
            )


def build_player_status_rows(
    state: PublicGameState,
    *,
    human_player_id: str,
) -> list[PlayerStatusRow]:
    """Build compact player status rows."""
    return [
        PlayerStatusRow(
            player_id=player.id,
            name=player.name,
            alive=player.alive,
            status_key="alive" if player.alive else "dead",
            relation_key="you" if player.id == human_player_id else None,
            updated_at=state.updated_at,
        )
        for player in state.players
    ]
