"""Session-scoped Streamlit display preferences."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from pydantic import BaseModel, ConfigDict

from werewolf_agent.clients.streamlit.i18n import Language, normalize_language
from werewolf_agent.clients.streamlit.state import KEY_STREAMLIT_PREFERENCES


class StreamlitPreferences(BaseModel):
    """Preferences shared by every Streamlit workspace."""

    language: Language | None = None

    model_config = ConfigDict(extra="forbid")


def preferences(session: MutableMapping[str, Any]) -> StreamlitPreferences:
    """Return validated preferences without leaking invalid session state."""
    value = session.get(KEY_STREAMLIT_PREFERENCES)
    if not isinstance(value, dict):
        return StreamlitPreferences()
    try:
        return StreamlitPreferences.model_validate(value)
    except ValueError:
        return StreamlitPreferences()


def preferred_language(session: MutableMapping[str, Any], default: Language) -> Language:
    """Return the selected language or the runtime default."""
    return preferences(session).language or default


def remember_language(session: MutableMapping[str, Any], language: str) -> None:
    """Store a normalized language selection."""
    value = preferences(session).model_copy(update={"language": normalize_language(language)})
    session[KEY_STREAMLIT_PREFERENCES] = value.model_dump(mode="json", exclude_none=True)


__all__ = ["StreamlitPreferences", "preferred_language", "remember_language"]
