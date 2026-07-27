"""Default Streamlit UI icon mappings."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UiIcon:
    """Small UI marker that can later be replaced by image assets."""

    symbol: str
    tone: str = "neutral"


DEFAULT_EVENT_ICON = UiIcon("•")
DEFAULT_ACTION_ICON = UiIcon("•")
DEFAULT_STATUS_ICON = UiIcon("•")

EVENT_ICONS: dict[str, UiIcon] = {
    "game_started": UiIcon("▶", "day"),
    "phase_started": UiIcon("↪", "day"),
    "speech_recorded": UiIcon("💬", "safe"),
    "vote_submitted": UiIcon("☑", "safe"),
    "vote_resolved": UiIcon("⚖", "day"),
    "night_resolved": UiIcon("◑", "danger"),
    "game_finished": UiIcon("🏁", "danger"),
}

ACTION_ICONS: dict[str, UiIcon] = {
    "speech": UiIcon("💬", "safe"),
    "vote": UiIcon("☑", "day"),
    "use_ability": UiIcon("◇", "safe"),
    "pass": UiIcon("▷", "neutral"),
}

STATUS_ICONS: dict[str, UiIcon] = {
    "phase": UiIcon("◌", "day"),
    "next_update": UiIcon("↻", "day"),
    "alive": UiIcon("●", "safe"),
    "turn": UiIcon("▶", "day"),
    "hand": UiIcon("✋", "danger"),
    "player": UiIcon("●", "neutral"),
    "updated": UiIcon("↺", "neutral"),
    "status": UiIcon("■", "neutral"),
    "winner": UiIcon("🏁", "neutral"),
}


def event_icon(event_type: str) -> UiIcon:
    """Return the configured marker for one public timeline event."""
    return EVENT_ICONS.get(event_type, DEFAULT_EVENT_ICON)


def action_icon(action_type: str) -> UiIcon:
    """Return the configured marker for one action."""
    return ACTION_ICONS.get(action_type, DEFAULT_ACTION_ICON)


def status_icon(status_type: str) -> UiIcon:
    """Return the configured marker for one status metric."""
    return STATUS_ICONS.get(status_type, DEFAULT_STATUS_ICON)
