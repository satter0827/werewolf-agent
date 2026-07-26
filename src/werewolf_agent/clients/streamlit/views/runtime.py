"""Playable Streamlit interface for one manual player."""

from __future__ import annotations

import importlib
import logging
from typing import Any
from uuid import uuid4

from werewolf_agent.adapters.auth import (
    SupabaseSession,
    bind_session,
    ensure_session,
    require_supabase_client_config,
)
from werewolf_agent.clients.streamlit.events import (
    LOG_STREAMLIT_APPLICATION_ERROR_HANDLED,
)
from werewolf_agent.clients.streamlit.i18n import (
    I18nCatalog,
    Language,
    load_i18n,
)
from werewolf_agent.clients.streamlit.operations import (
    load_game_screen,
    load_runtime_config,
    log_streamlit_rerun_started,
)
from werewolf_agent.clients.streamlit.screens import (
    ScreenCatalog,
    load_screen_catalog,
)
from werewolf_agent.clients.streamlit.setup import (
    VIEW_APP_SETTINGS,
    VIEW_GAME,
    VIEW_HISTORY,
    VIEW_OBSERVE_SETUP,
    preferred_language,
)
from werewolf_agent.clients.streamlit.state import (
    pause_auto_advance,
    sync_auto_advance_game,
)
from werewolf_agent.clients.streamlit.styles import load_style_tag
from werewolf_agent.clients.streamlit.views.game import _render_game_screen
from werewolf_agent.clients.streamlit.views.history import _render_history_screen
from werewolf_agent.clients.streamlit.views.settings import _render_settings_screen
from werewolf_agent.clients.streamlit.views.setup import _render_setup_screen
from werewolf_agent.clients.streamlit.views.sidebar import _render_sidebar
from werewolf_agent.contracts import (
    AppError,
)
from werewolf_agent.contracts.error_catalog import get_error_spec
from werewolf_agent.observability import bind_observation_context, configure_entrypoint_logging
from werewolf_agent.observability.constants import (
    EVENT_OUTCOME_FAILURE,
)
from werewolf_agent.observability.levels import log_level_number
from werewolf_agent.security.redaction import redact_text
from werewolf_agent.settings import (
    AppSettings,
    get_settings,
)

logger = logging.getLogger(__name__)
STREAMLIT_AUTH_SESSION_KEY = "_auth_session"


class _StreamlitSessionStore:
    """Keep credentials in one server-side Streamlit browser session."""

    def __init__(self, state: Any) -> None:
        self._state = state

    def load(self) -> SupabaseSession | None:
        value = self._state.get(STREAMLIT_AUTH_SESSION_KEY)
        return value if isinstance(value, SupabaseSession) else None

    def save(self, session: SupabaseSession) -> None:
        self._state[STREAMLIT_AUTH_SESSION_KEY] = session

    def clear(self) -> None:
        self._state.pop(STREAMLIT_AUTH_SESSION_KEY, None)


def main() -> None:
    """Render the Streamlit application."""
    st = _streamlit()
    settings = get_settings()
    configure_entrypoint_logging(
        settings,
        default_log_file_name="streamlit.jsonl",
        service_name=settings.streamlit_service_name,
    )
    with bind_observation_context(trace_id=str(uuid4())):
        log_streamlit_rerun_started(settings)
        _render_app(st, settings)


def _render_app(st: Any, settings: AppSettings) -> None:
    """Render one Streamlit rerun with a bound observation context."""
    catalog = load_i18n(settings)
    screens = load_screen_catalog(settings)
    lang = preferred_language(st.session_state, settings.streamlit_language)
    st.set_page_config(
        page_title=settings.streamlit_page_title,
        page_icon="🐺",
        layout="wide",
        initial_sidebar_state=settings.streamlit_initial_sidebar_state,
    )
    st.markdown(load_style_tag(settings), unsafe_allow_html=True)
    session_store = _StreamlitSessionStore(st.session_state)
    try:
        require_supabase_client_config(settings)
        session = ensure_session(settings, store=session_store)
    except AppError as exc:
        _handle_app_error(st, exc)
        return

    with bind_session(session):
        _render_session_app(
            st,
            settings,
            catalog=catalog,
            lang=lang,
            screens=screens,
            session_store=session_store,
        )


def _render_session_app(
    st: Any,
    settings: AppSettings,
    *,
    catalog: I18nCatalog,
    lang: Language,
    screens: ScreenCatalog,
    session_store: _StreamlitSessionStore,
) -> None:
    """Render authenticated or guest content with a request-scoped HTTP token."""
    selected_option, view = _render_sidebar(
        st,
        settings,
        catalog=catalog,
        lang=lang,
        screens=screens,
        session_store=session_store,
    )
    if view == VIEW_APP_SETTINGS:
        _render_settings_screen(
            st,
            settings=settings,
            catalog=catalog,
            lang=lang,
            screens=screens,
        )
        return
    if view == VIEW_HISTORY:
        _render_history_screen(
            st,
            settings=settings,
            catalog=catalog,
            lang=lang,
        )
        return
    if view != VIEW_GAME or selected_option is None:
        _render_setup_screen(
            st,
            settings=settings,
            catalog=catalog,
            lang=lang,
            observer=view == VIEW_OBSERVE_SETUP,
            screens=screens,
        )
        return

    sync_auto_advance_game(st.session_state, selected_option.game_id)
    try:
        runtime_config = load_runtime_config(settings=settings)
        screen = load_game_screen(
            settings=settings,
            game_id=selected_option.game_id,
            manual_player_id=selected_option.manual_player_id,
            screen_mode=selected_option.mode,
            catalog=catalog,
            lang=lang,
        )
    except AppError as exc:
        st.error(exc.detail)
        return
    if selected_option.mode != "playable" or screen.can_submit_action or screen.is_completed:
        pause_auto_advance(st.session_state)

    _render_game_screen(
        st,
        settings=settings,
        screen=screen,
        selected_option=selected_option,
        catalog=catalog,
        lang=lang,
        message_max_chars=runtime_config.limits.message_max_chars,
        screens=screens,
    )


def _streamlit() -> Any:
    return importlib.import_module("streamlit")


def _handle_app_error(st: Any, exc: AppError) -> None:
    logger.log(
        log_level_number(get_error_spec(exc.code).log_level),
        LOG_STREAMLIT_APPLICATION_ERROR_HANDLED,
        extra={
            **exc.log_extra(),
            "error_message": redact_text(exc.detail),
            "error.message": redact_text(exc.detail),
            "event_action": LOG_STREAMLIT_APPLICATION_ERROR_HANDLED,
            "event_outcome": EVENT_OUTCOME_FAILURE,
        },
    )
    st.error(redact_text(exc.detail))
