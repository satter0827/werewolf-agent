"""Session-state keys and helpers for the Streamlit entry point."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

KEY_API_URL = "werewolf_streamlit_api_url"
KEY_SELECTED_SAVE_ID = "werewolf_streamlit_selected_save_id"
KEY_MESSAGE = "werewolf_streamlit_message"
KEY_CONTROL_TOKENS = "werewolf_streamlit_control_tokens"


def text_value(session: MutableMapping[str, Any], key: str, default: str = "") -> str:
    """Return a text value from session state."""
    value = session.get(key, default)
    return str(value) if value is not None else default


def remember_selected_save(session: MutableMapping[str, Any], option_id: str) -> None:
    """Store the selected save option id."""
    session[KEY_SELECTED_SAVE_ID] = option_id


def remember_control_token(
    session: MutableMapping[str, Any],
    *,
    slot_id: str,
    control_token: str,
) -> None:
    """Store one playable token in the current Streamlit session only."""
    slot_id_text = slot_id.strip()
    token_text = control_token.strip()
    if not slot_id_text or not token_text:
        return
    tokens = control_tokens_by_slot(session)
    tokens[slot_id_text] = token_text
    session[KEY_CONTROL_TOKENS] = tokens


def control_tokens_by_slot(session: MutableMapping[str, Any]) -> dict[str, str]:
    """Return playable tokens held only by the current Streamlit session."""
    value = session.get(KEY_CONTROL_TOKENS)
    if not isinstance(value, dict):
        return {}
    return {
        str(slot_id): str(token)
        for slot_id, token in value.items()
        if str(slot_id).strip() and str(token).strip()
    }


def clear_message(session: MutableMapping[str, Any]) -> None:
    """Clear the current action message."""
    session.pop(KEY_MESSAGE, None)
