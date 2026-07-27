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
from werewolf_agent.clients.streamlit.setup import (
    VIEW_ADMIN,
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
from werewolf_agent.clients.streamlit.views.errors import render_app_error
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
_WORKSPACE_NAVIGATION = {
    "play": ("nav.play", VIEW_PLAY_SETUP),
    "observe": ("nav.observe", VIEW_OBSERVE_SETUP),
    "records": ("nav.records", VIEW_HISTORY),
    "admin": ("nav.admin", VIEW_ADMIN),
    "preferences": ("nav.preferences", VIEW_APP_SETTINGS),
}
_WORKSPACE_ORDER = ("play", "observe", "records", "admin", "preferences")


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
    session_store: SessionStore | None = None,
    is_admin: bool = False,
) -> tuple[SavedGameOptionView | None, str]:
    selected_option: SavedGameOptionView | None = None

    _render_sidebar_brand(st, catalog=catalog, lang=lang)
    if session_store is not None:
        _render_sidebar_auth(
            st,
            settings=settings,
            session_store=session_store,
            catalog=catalog,
            lang=lang,
        )
    st.sidebar.divider()
    st.sidebar.subheader(catalog.t(lang, "sidebar.history"))
    selected_option = _render_history_selector(
        st,
        settings=settings,
        catalog=catalog,
        lang=lang,
    )
    st.sidebar.divider()
    st.sidebar.subheader(catalog.t(lang, "sidebar.navigation"))
    _render_sidebar_navigation(st, catalog=catalog, lang=lang, is_admin=is_admin)
    return selected_option, current_view(st.session_state)


def _render_sidebar_auth(
    st: Any,
    *,
    settings: AppSettings,
    session_store: SessionStore,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    """Render guest/member controls without exposing session credentials."""
    session = session_store.load()
    if session is not None and not session.is_anonymous:
        st.sidebar.caption(session.email or catalog.t(lang, "auth.signed_in"))
        if st.sidebar.button(catalog.t(lang, "auth.sign_out"), use_container_width=True):
            try:
                sign_out(settings, store=session_store)
            except AppError as exc:
                render_app_error(st.sidebar, exc, lang=lang)
                return
            st.rerun()
        return

    st.sidebar.caption(catalog.t(lang, "auth.guest"))
    with st.sidebar.expander(catalog.t(lang, "auth.sign_in")):
        with st.form("account_login"):
            email = st.text_input(catalog.t(lang, "auth.email"), max_chars=254)
            password = st.text_input(
                catalog.t(lang, "auth.password"),
                type="password",
                max_chars=128,
            )
            submitted = st.form_submit_button(
                catalog.t(lang, "auth.sign_in"), use_container_width=True
            )
        if submitted:
            try:
                sign_in_with_password(
                    settings,
                    email,
                    password,
                    store=session_store,
                )
            except AppError as exc:
                render_app_error(st, exc, lang=lang)
                return
            st.rerun()


def _render_sidebar_navigation(
    st: Any,
    *,
    catalog: I18nCatalog,
    lang: Language,
    is_admin: bool = False,
) -> None:
    """Render sidebar navigation controls."""
    for workspace, label_key, view in _navigation_items(is_admin=is_admin):
        if st.sidebar.button(
            catalog.t(lang, label_key),
            key=f"navigation_{workspace}",
            type="primary" if current_view(st.session_state) == view else "secondary",
            use_container_width=True,
        ):
            switch_view(st.session_state, view)
            st.rerun()


def _render_unavailable_navigation(
    st: Any,
    *,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    """Render configured workspaces as disabled during degraded operation."""
    st.sidebar.subheader(catalog.t(lang, "sidebar.navigation"))
    for workspace, label_key, _view in _navigation_items(is_admin=False):
        st.sidebar.button(
            catalog.t(lang, label_key),
            key=f"unavailable_navigation_{workspace}",
            use_container_width=True,
            disabled=True,
        )
    st.sidebar.caption(catalog.t(lang, "runtime.navigation_unavailable"))


def _navigation_items(*, is_admin: bool) -> list[tuple[str, str, str]]:
    return [
        (workspace, *_WORKSPACE_NAVIGATION[workspace])
        for workspace in _WORKSPACE_ORDER
        if workspace != "admin" or is_admin
    ]


def _render_sidebar_brand(st: Any, *, catalog: I18nCatalog, lang: Language) -> None:
    st.sidebar.markdown(
        f"""
        <div class="wa-sidebar-brand">
                <div>
                    <div class="wa-brand-title">Werewolf Agent</div>
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
