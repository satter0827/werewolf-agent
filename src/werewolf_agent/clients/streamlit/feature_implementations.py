"""Concrete Streamlit renderers that declare API feature ownership."""

from collections.abc import Callable
from typing import Any, Final

from werewolf_agent.clients.streamlit.views.admin import _render_admin_screen
from werewolf_agent.clients.streamlit.views.game import _render_game_screen
from werewolf_agent.clients.streamlit.views.game_settings import _render_game_settings_screen
from werewolf_agent.clients.streamlit.views.history import _render_history_screen
from werewolf_agent.clients.streamlit.views.runtime import _render_app
from werewolf_agent.clients.streamlit.views.setup import _render_setup_screen

STREAMLIT_FEATURE_IMPLEMENTATIONS: Final[dict[str, Callable[..., Any]]] = {
    "shell": _render_app,
    "setup": _render_setup_screen,
    "game_settings": _render_game_settings_screen,
    "game": _render_game_screen,
    "records": _render_history_screen,
    "admin": _render_admin_screen,
}

__all__ = ["STREAMLIT_FEATURE_IMPLEMENTATIONS"]
