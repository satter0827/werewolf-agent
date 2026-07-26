"""Consistent Streamlit error and recovery rendering."""

from __future__ import annotations

from typing import Any

from werewolf_agent.clients.presentation import present_error
from werewolf_agent.clients.streamlit.i18n import Language
from werewolf_agent.contracts import AppError
from werewolf_agent.security.redaction import redact_text


def render_app_error(st: Any, error: AppError, *, lang: Language) -> None:
    """Render safe state followed by an actionable recovery instruction."""
    presentation = present_error(error, language=lang)
    st.error(redact_text(presentation.detail))
    if presentation.next_action:
        prefix = "必要な対応" if lang == "ja" else "Required action"
        st.info(f"{prefix}: {presentation.next_action}")


__all__ = ["render_app_error"]
