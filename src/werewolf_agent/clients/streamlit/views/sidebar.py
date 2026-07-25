"""Playable Streamlit interface for one manual player."""

from __future__ import annotations

import logging
from typing import Any, Protocol, cast

from werewolf_agent.adapters.auth import (
    sign_in_with_password,
    sign_out,
)
from werewolf_agent.clients.streamlit.history import (
    build_history_options,
)
from werewolf_agent.clients.streamlit.i18n import (
    I18nCatalog,
    Language,
)
from werewolf_agent.clients.streamlit.operations import (
    list_recent_games,
)
from werewolf_agent.clients.streamlit.screens import (
    ScreenCatalog,
)
from werewolf_agent.clients.streamlit.setup import (
    VIEW_APP_SETTINGS,
    VIEW_GAME,
    VIEW_HISTORY,
    VIEW_OBSERVE_SETUP,
    VIEW_PLAY_SETUP,
    current_view,
    switch_view,
)
from werewolf_agent.clients.streamlit.state import (
    KEY_SELECTED_HISTORY_ID,
    active_game_selection,
    remember_selected_history,
    text_value,
)
from werewolf_agent.clients.streamlit.view_models import (
    SavedGameOptionView,
)
from werewolf_agent.clients.streamlit.views.game import (
    _selected_option_by_id,
    _selected_option_index,
)
from werewolf_agent.contracts import (
    AppError,
)
from werewolf_agent.settings import (
    AppSettings,
)

logger = logging.getLogger(__name__)
STREAMLIT_AUTH_SESSION_KEY = "_auth_session"


class SessionStore(Protocol):
    """Authentication session operations required by the sidebar."""

    def load(self) -> Any:
        """Return the current authentication session."""

    def save(self, session: Any) -> None:
        """Store the current authentication session."""

    def clear(self) -> None:
        """Remove the current authentication session."""


def _render_sidebar(
    st: Any,
    settings: AppSettings,
    *,
    catalog: I18nCatalog,
    lang: Language,
    screens: ScreenCatalog,
    session_store: SessionStore | None = None,
) -> tuple[SavedGameOptionView | None, str]:
    selected_option: SavedGameOptionView | None = None

    for element in screens.elements("sidebar", "main"):
        if element.id == "brand":
            _render_sidebar_brand(st, catalog=catalog, lang=lang)
            if session_store is not None:
                _render_sidebar_auth(st, settings=settings, session_store=session_store)
        elif element.id == "history_selector":
            st.sidebar.divider()
            st.sidebar.subheader(catalog.t(lang, "sidebar.history"))
            selected_option = _render_history_selector(
                st,
                settings=settings,
                catalog=catalog,
                lang=lang,
            )
        elif element.id == "navigation":
            st.sidebar.divider()
            st.sidebar.subheader(catalog.t(lang, "sidebar.navigation"))
            _render_sidebar_navigation(st, catalog=catalog, lang=lang)
    return selected_option, current_view(st.session_state)


def _render_sidebar_auth(
    st: Any,
    *,
    settings: AppSettings,
    session_store: SessionStore,
) -> None:
    """Render guest/member controls without exposing session credentials."""
    session = session_store.load()
    if session is not None and not session.is_anonymous:
        st.sidebar.caption(session.email or "ログイン中")
        if st.sidebar.button("ログアウト", use_container_width=True):
            try:
                sign_out(settings, store=session_store)
            except AppError as exc:
                st.sidebar.error(exc.detail)
                return
            st.rerun()
        return

    st.sidebar.caption("ゲストで利用中")
    with st.sidebar.expander("ログイン"):
        with st.form("account_login"):
            email = st.text_input("メールアドレス", max_chars=254)
            password = st.text_input(
                "パスワード",
                type="password",
                max_chars=128,
            )
            submitted = st.form_submit_button("ログイン", use_container_width=True)
        if submitted:
            try:
                sign_in_with_password(
                    settings,
                    email,
                    password,
                    store=session_store,
                )
            except AppError as exc:
                st.error(exc.detail)
                return
            st.rerun()


def _render_sidebar_navigation(st: Any, *, catalog: I18nCatalog, lang: Language) -> None:
    """Render sidebar navigation controls."""
    if st.sidebar.button(f"▶ {catalog.t(lang, 'nav.play')}", use_container_width=True):
        switch_view(st.session_state, VIEW_PLAY_SETUP)
        st.rerun()
    if st.sidebar.button(f"◉ {catalog.t(lang, 'nav.observe')}", use_container_width=True):
        switch_view(st.session_state, VIEW_OBSERVE_SETUP)
        st.rerun()
    if st.sidebar.button(f"▣ {catalog.t(lang, 'nav.history')}", use_container_width=True):
        switch_view(st.session_state, VIEW_HISTORY)
        st.rerun()
    if st.sidebar.button(f"⚙ {catalog.t(lang, 'nav.settings')}", use_container_width=True):
        switch_view(st.session_state, VIEW_APP_SETTINGS)
        st.rerun()


def _render_sidebar_brand(st: Any, *, catalog: I18nCatalog, lang: Language) -> None:
    st.sidebar.markdown(
        f"""
        <div class="wa-sidebar-brand">
                <div class="wa-brand-mark">🐺</div>
                <div>
                    <h1 class="wa-brand-title">Werewolf Agent</h1>
                    <div class="wa-brand-mode">{catalog.t(lang, "brand.mode")}</div>
                </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_history_selector(
    st: Any,
    *,
    settings: AppSettings,
    catalog: I18nCatalog,
    lang: Language,
) -> SavedGameOptionView | None:
    try:
        games = list_recent_games(settings=settings)
    except AppError:
        games = []
        st.sidebar.caption(catalog.t(lang, "history.unavailable"))
    options = build_history_options(
        active_game_selection(st.session_state),
        games,
        catalog=catalog,
        lang=lang,
    )
    if not options:
        st.sidebar.caption(catalog.t(lang, "history.empty"))
        return None

    selected_id = text_value(st.session_state, KEY_SELECTED_HISTORY_ID)
    index = _selected_option_index(options, selected_id)
    selected_option = st.sidebar.selectbox(
        catalog.t(lang, "history.selector"),
        options,
        index=index,
        format_func=lambda option: option.label,
    )
    selected_option = cast(SavedGameOptionView, selected_option)
    if st.sidebar.button(catalog.t(lang, "history.open"), use_container_width=True):
        remember_selected_history(st.session_state, selected_option.option_id)
        switch_view(st.session_state, VIEW_GAME)
        st.rerun()
    if current_view(st.session_state) != VIEW_GAME:
        return None
    return _selected_option_by_id(options, text_value(st.session_state, KEY_SELECTED_HISTORY_ID))
