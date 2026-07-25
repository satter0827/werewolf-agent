"""Purpose-specific Streamlit display models and projections."""

from werewolf_agent.clients.streamlit.view_models.actions import (
    action_choice,
    current_turn_detail,
    current_turn_title,
    hand_panel_view,
    observation_view_from_response,
    target_candidates_for_action,
)
from werewolf_agent.clients.streamlit.view_models.game import (
    build_game_screen_view,
    game_option_label,
    observation_memo_view,
    player_seats,
    status_metrics,
    table_legend_items,
)
from werewolf_agent.clients.streamlit.view_models.timeline import (
    observer_log_view,
    result_summary_view,
    timeline_items,
)
from werewolf_agent.clients.streamlit.view_models.types import (
    ActionChoiceView,
    GameScreenView,
    HandPanelView,
    ObservationMemoView,
    ObservationView,
    ObserverLogView,
    PlayerSeatView,
    ResultSummaryView,
    SavedGameOptionView,
    ScreenMode,
    StatusMetricView,
    TableLegendItemView,
    TimelineItemView,
)

__all__ = [
    "ActionChoiceView",
    "GameScreenView",
    "HandPanelView",
    "ObservationMemoView",
    "ObservationView",
    "ObserverLogView",
    "PlayerSeatView",
    "ResultSummaryView",
    "SavedGameOptionView",
    "ScreenMode",
    "StatusMetricView",
    "TableLegendItemView",
    "TimelineItemView",
    "action_choice",
    "build_game_screen_view",
    "current_turn_detail",
    "current_turn_title",
    "game_option_label",
    "hand_panel_view",
    "observation_memo_view",
    "observation_view_from_response",
    "observer_log_view",
    "player_seats",
    "result_summary_view",
    "status_metrics",
    "table_legend_items",
    "target_candidates_for_action",
    "timeline_items",
]
