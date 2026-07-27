"""Streamlit display preferences."""

from __future__ import annotations

from typing import Any

from werewolf_agent.clients.streamlit.i18n import I18nCatalog, Language
from werewolf_agent.clients.streamlit.preferences import remember_language
from werewolf_agent.settings import AppSettings


def _render_settings_screen(
    st: Any,
    *,
    settings: AppSettings,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    """Render preferences that do not belong to a game setup document."""
    st.title(catalog.t(lang, "settings.title"))
    st.caption("画面表示に関する設定を変更します。ゲーム内容は「ゲーム設定」で管理します。")
    language_codes = list(catalog.languages)
    selected_language = st.selectbox(
        catalog.t(lang, "settings.language"),
        language_codes,
        index=language_codes.index(lang) if lang in language_codes else 0,
        format_func=lambda value: catalog.languages[value],
    )
    if selected_language != lang:
        remember_language(st.session_state, str(selected_language))
        st.rerun()


__all__ = ["_render_settings_screen"]
