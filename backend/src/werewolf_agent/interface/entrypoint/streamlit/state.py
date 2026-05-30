"""Session-state keys and helpers for the Streamlit entry point."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

KEY_API_URL = "werewolf_streamlit_api_url"
KEY_SELECTED_SAVE_ID = "werewolf_streamlit_selected_save_id"
KEY_MESSAGE = "werewolf_streamlit_message"


def text_value(session: MutableMapping[str, Any], key: str, default: str = "") -> str:
    """Return a text value from session state."""
    value = session.get(key, default)
    return str(value) if value is not None else default


def remember_selected_save(session: MutableMapping[str, Any], option_id: str) -> None:
    """Store the selected save option id."""
    session[KEY_SELECTED_SAVE_ID] = option_id


def clear_message(session: MutableMapping[str, Any]) -> None:
    """Clear the current action message."""
    session.pop(KEY_MESSAGE, None)
