"""Streamlit workspace navigation state."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

KEY_CURRENT_VIEW = "werewolf_streamlit_current_view"
KEY_PENDING_VIEW_SCROLL = "werewolf_streamlit_pending_view_scroll"

VIEW_PLAY_SETUP = "play_setup"
VIEW_OBSERVE_SETUP = "observe_setup"
VIEW_HISTORY = "history"
VIEW_GAME = "game"
VIEW_APP_SETTINGS = "app_settings"
VIEW_GAME_SETTINGS = "game_settings"
VIEW_ADMIN = "admin"
VIEWS = frozenset(
    {
        VIEW_PLAY_SETUP,
        VIEW_OBSERVE_SETUP,
        VIEW_HISTORY,
        VIEW_GAME,
        VIEW_APP_SETTINGS,
        VIEW_GAME_SETTINGS,
        VIEW_ADMIN,
    }
)


def current_view(session: MutableMapping[str, Any]) -> str:
    """Return the normalized current workspace view."""
    view = str(session.get(KEY_CURRENT_VIEW, VIEW_PLAY_SETUP))
    return view if view in VIEWS else VIEW_PLAY_SETUP


def switch_view(session: MutableMapping[str, Any], view: str) -> None:
    """Select a workspace view and request scroll restoration."""
    next_view = view if view in VIEWS else VIEW_PLAY_SETUP
    if current_view(session) == next_view:
        return
    session[KEY_CURRENT_VIEW] = next_view
    session[KEY_PENDING_VIEW_SCROLL] = True


def consume_pending_view_scroll(session: MutableMapping[str, Any]) -> bool:
    """Consume the one-shot scroll request after view navigation."""
    return bool(session.pop(KEY_PENDING_VIEW_SCROLL, False))


__all__ = [
    "VIEW_ADMIN",
    "VIEW_APP_SETTINGS",
    "VIEW_GAME",
    "VIEW_GAME_SETTINGS",
    "VIEW_HISTORY",
    "VIEW_OBSERVE_SETUP",
    "VIEW_PLAY_SETUP",
    "consume_pending_view_scroll",
    "current_view",
    "switch_view",
]
