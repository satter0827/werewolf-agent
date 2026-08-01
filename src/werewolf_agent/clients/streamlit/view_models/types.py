"""Typed display values for Streamlit game projections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from werewolf_agent.clients.streamlit.constants import DEFAULT_NARRATION_MODE
from werewolf_agent.contracts.constants import DEFAULT_DELIBERATION_LEVEL

ScreenMode = Literal["playable", "observer"]


@dataclass(frozen=True)
class SavedGameOptionView:
    """One save option shown in the sidebar selector."""

    option_id: str
    label: str
    game_id: str
    mode: ScreenMode
    manual_player_id: str | None = None
    seed: int | None = None
    narration_mode: str = DEFAULT_NARRATION_MODE
    deliberation_level: str = DEFAULT_DELIBERATION_LEVEL


@dataclass(frozen=True)
class PlayerSeatView:
    """One compact player seat in the game table."""

    player_id: str
    name: str
    status: str
    activity: str
    activity_tone: str
    is_alive: bool
    is_manual: bool
    is_current: bool


@dataclass(frozen=True)
class StatusMetricView:
    """One top status strip item."""

    key: str
    icon: str
    label: str
    value: str
    detail: str
    tone: str = "neutral"


@dataclass(frozen=True)
class TableLegendItemView:
    """One table legend marker."""

    symbol: str
    label: str
    tone: str


@dataclass(frozen=True)
class ActionChoiceView:
    """One action option visible in the hand panel."""

    action_type: str
    ability_id: str | None
    icon: str
    label: str
    requires_target: bool
    requires_message: bool


@dataclass(frozen=True)
class HandPanelView:
    """Right-side player hand panel state."""

    heading: str
    title: str
    detail: str
    tone: str
    advance_title: str
    advance_detail: str
    can_advance: bool


@dataclass(frozen=True)
class TimelineItemView:
    """One public timeline row."""

    sequence: int
    icon: str
    tone: str
    title: str
    detail: str
    time_text: str
    day_label: str


@dataclass(frozen=True)
class ObservationView:
    """Private information visible only to the controlled player."""

    role: str
    available_actions: list[str]
    action_choices: list[ActionChoiceView]
    known_role_lines: list[str]
    target_candidates: dict[str, list[str]]
    reference_choices: dict[str, str]
    reference_topics: dict[str, str]
    reference_positions: dict[str, str]
    discussion_topic_ids: list[str]
    vote_evidence_choices: dict[str, dict[str, str]]
    action_text_limits: dict[str, int]


@dataclass(frozen=True)
class ObserverLogView:
    """Observer-only summary built from the public timeline."""

    title: str
    entries_title: str
    entries: list[str]
    empty_text: str


@dataclass(frozen=True)
class ResultSummaryView:
    """Completed-game result summary displayed after the timeline."""

    title: str
    detail: str
    facts: list[str]


@dataclass(frozen=True)
class ObservationMemoView:
    """Public observation memo shown at the bottom of the right panel."""

    title: str
    updated_label: str
    lines: list[str]


@dataclass(frozen=True)
class GameScreenView:
    """Single display model for the Streamlit game screen."""

    game_id: str
    screen_mode: ScreenMode
    status: str
    phase: str
    phase_label: str
    day_label: str
    status_label: str
    alive_label: str
    turn_label: str
    player_label: str
    updated_label: str
    winner_label: str
    player_count: int
    alive_count: int
    status_metrics: list[StatusMetricView]
    table_legend: list[TableLegendItemView]
    seats: list[PlayerSeatView]
    timeline: list[TimelineItemView]
    hand_panel: HandPanelView
    observation: ObservationView | None
    observer_log: ObserverLogView | None
    result_summary: ResultSummaryView | None
    observation_memo: ObservationMemoView
    current_turn_title: str
    current_turn_detail: str
    is_completed: bool
    can_submit_action: bool
