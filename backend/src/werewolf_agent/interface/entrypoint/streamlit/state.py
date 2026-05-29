"""Session-state keys and helpers for the Streamlit entry point."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

KEY_API_URL = "werewolf_api_url"
KEY_GAME_ID = "werewolf_game_id"
KEY_HUMAN_PLAYER_ID = "werewolf_human_player_id"
KEY_CONTROL_TOKEN = "werewolf_control_token"
KEY_MESSAGE = "werewolf_message"


def text_value(session: MutableMapping[str, Any], key: str, default: str = "") -> str:
    """Return a text value from session state."""
    value = session.get(key, default)
    return str(value) if value is not None else default


def set_game_session(
    session: MutableMapping[str, Any],
    *,
    game_id: str,
    human_player_id: str,
    control_token: str,
) -> None:
    """Store the active playable game context."""
    session[KEY_GAME_ID] = game_id
    session[KEY_HUMAN_PLAYER_ID] = human_player_id
    session[KEY_CONTROL_TOKEN] = control_token


def clear_game_session(session: MutableMapping[str, Any]) -> None:
    """Clear the active game context while preserving connection settings."""
    for key in (KEY_GAME_ID, KEY_HUMAN_PLAYER_ID, KEY_CONTROL_TOKEN, KEY_MESSAGE):
        session.pop(key, None)
