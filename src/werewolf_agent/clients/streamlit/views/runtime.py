"""Playable Streamlit interface for one manual player."""

from __future__ import annotations

import atexit
import importlib
import logging
import threading
from typing import Any
from uuid import uuid4

from werewolf_agent.adapters.auth import (
    SupabaseSession,
    bind_session,
    ensure_session,
    require_supabase_client_config,
)
from werewolf_agent.clients.presentation import implements_features
from werewolf_agent.clients.streamlit.events import (
    LOG_STREAMLIT_APPLICATION_ERROR_HANDLED,
    LOG_STREAMLIT_APPLICATION_STARTED,
    LOG_STREAMLIT_APPLICATION_STOPPED,
)
from werewolf_agent.clients.streamlit.i18n import (
    I18nCatalog,
    Language,
    load_i18n,
)
from werewolf_agent.clients.streamlit.operations import (
    load_game_screen,
    load_runtime_config,
    load_runtime_status,
    load_session,
    log_streamlit_rerun_started,
)
from werewolf_agent.clients.streamlit.preferences import preferred_language, remember_language
from werewolf_agent.clients.streamlit.setup import (
    VIEW_ADMIN,
    VIEW_APP_SETTINGS,
    VIEW_GAME,
    VIEW_GAME_SETTINGS,
    VIEW_HISTORY,
    VIEW_OBSERVE_SETUP,
    consume_pending_view_scroll,
)
from werewolf_agent.clients.streamlit.state import (
    pause_auto_advance,
    sync_auto_advance_game,
)
from werewolf_agent.clients.streamlit.styles import load_style_tag
from werewolf_agent.clients.streamlit.views.admin import _render_admin_screen
from werewolf_agent.clients.streamlit.views.errors import render_app_error
from werewolf_agent.clients.streamlit.views.game import _render_game_screen
from werewolf_agent.clients.streamlit.views.game_settings import _render_game_settings_screen
from werewolf_agent.clients.streamlit.views.history import _render_history_screen
from werewolf_agent.clients.streamlit.views.settings import _render_settings_screen
from werewolf_agent.clients.streamlit.views.setup import _render_setup_screen
from werewolf_agent.clients.streamlit.views.sidebar import (
    _render_sidebar,
    _render_unavailable_navigation,
)
from werewolf_agent.contracts import (
    AppError,
)
from werewolf_agent.contracts.error_catalog import get_error_spec
from werewolf_agent.observability import bind_observation_context, configure_entrypoint_logging
from werewolf_agent.observability.constants import (
    EVENT_OUTCOME_FAILURE,
    EVENT_OUTCOME_SUCCESS,
)
from werewolf_agent.observability.levels import log_level_number
from werewolf_agent.security.redaction import redact_text
from werewolf_agent.settings import (
    AppSettings,
)

logger = logging.getLogger(__name__)
STREAMLIT_AUTH_SESSION_KEY = "_auth_session"
_PROCESS_LIFECYCLE_LOCK = threading.Lock()
_PROCESS_STARTED = False
_VIEW_SCROLL_SCRIPT = """
<script>
const resetViewScroll = () => {
  const parentDocument = window.parent.document;
  const containers = [
    parentDocument.scrollingElement,
    parentDocument.querySelector('[data-testid="stAppViewContainer"]'),
    parentDocument.querySelector('[data-testid="stMain"]'),
  ];
  window.parent.scrollTo({ top: 0, left: 0, behavior: "auto" });
  containers.forEach((container) =>
    container?.scrollTo({ top: 0, left: 0, behavior: "auto" })
  );
};
window.parent.requestAnimationFrame(() =>
  window.parent.requestAnimationFrame(resetViewScroll)
);
</script>
"""


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
    settings = configure_entrypoint_logging(
        default_log_file_name="streamlit.jsonl",
        service_name="werewolf-agent-streamlit",
    )
    _log_process_started()
    with bind_observation_context(trace_id=str(uuid4())):
        log_streamlit_rerun_started(settings)
        _render_app(st, settings)


def _log_process_started() -> None:
    global _PROCESS_STARTED
    with _PROCESS_LIFECYCLE_LOCK:
        if _PROCESS_STARTED:
            return
        logger.info(
            LOG_STREAMLIT_APPLICATION_STARTED,
            extra={
                "event_action": LOG_STREAMLIT_APPLICATION_STARTED,
                "event_outcome": EVENT_OUTCOME_SUCCESS,
            },
        )
        atexit.register(_log_process_stopped)
        _PROCESS_STARTED = True


def _log_process_stopped() -> None:
    logger.info(
        LOG_STREAMLIT_APPLICATION_STOPPED,
        extra={
            "event_action": LOG_STREAMLIT_APPLICATION_STOPPED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
        },
    )


@implements_features("runtime_config_get", "runtime_status_get", "session_get")
def _render_app(st: Any, settings: AppSettings) -> None:
    """Render one Streamlit rerun with a bound observation context."""
    catalog = load_i18n(settings)
    lang = preferred_language(st.session_state, settings.streamlit_language)
    st.set_page_config(
        page_title=settings.streamlit_page_title,
        layout="wide",
        initial_sidebar_state=settings.streamlit_initial_sidebar_state,
    )
    st.markdown(
        load_style_tag(),
        unsafe_allow_html=True,
    )
    session_store = _StreamlitSessionStore(st.session_state)
    try:
        require_supabase_client_config(settings)
        session = ensure_session(settings, store=session_store)
    except AppError as exc:
        _log_app_error(exc)
        _render_degraded_shell(
            st,
            settings,
            catalog=catalog,
            lang=lang,
        )
    else:
        with bind_session(session):
            _render_session_app(
                st,
                settings,
                catalog=catalog,
                lang=lang,
                session_store=session_store,
            )


def _render_degraded_shell(
    st: Any,
    settings: AppSettings,
    *,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    """Keep diagnosis and display preferences available without authentication."""
    _render_unavailable_navigation(st, catalog=catalog, lang=lang)
    st.title(settings.streamlit_page_title)
    st.caption(catalog.t(lang, "runtime.degraded_caption"))
    st.warning(catalog.t(lang, "runtime.service_unavailable"))
    st.header(catalog.t(lang, "runtime.available_actions"))
    selected = st.selectbox(
        catalog.t(lang, "settings.language"),
        options=list(catalog.languages),
        format_func=lambda value: catalog.languages[value],
        index=list(catalog.languages).index(lang),
        key="degraded_language",
    )
    if selected != lang:
        remember_language(st.session_state, selected)
    st.info(catalog.t(lang, "runtime.auth_recovery"))


def _render_session_app(
    st: Any,
    settings: AppSettings,
    *,
    catalog: I18nCatalog,
    lang: Language,
    session_store: _StreamlitSessionStore,
) -> None:
    """Render authenticated or guest content with a request-scoped HTTP token."""
    try:
        session_info = load_session(settings=settings)
    except AppError:
        session_info = None
    try:
        runtime_status = load_runtime_status(settings=settings)
    except AppError:
        runtime_status = None
    database_available = _component_available(runtime_status, "database")
    queue_available = _component_available(runtime_status, "operation_queue")
    selected_option, view = _render_sidebar(
        st,
        settings,
        catalog=catalog,
        lang=lang,
        session_store=session_store,
        is_admin=session_info.administrator if session_info is not None else False,
    )
    _render_pending_view_scroll(st)
    if view == VIEW_ADMIN:
        if session_info is None or not session_info.administrator:
            st.error(catalog.t(lang, "admin.permission_unconfirmed"))
            return
        if not database_available:
            st.warning(catalog.t(lang, "runtime.database_required"))
            return
        _render_admin_screen(
            st,
            settings=settings,
            catalog=catalog,
            lang=lang,
        )
        return
    if view == VIEW_APP_SETTINGS:
        _render_settings_screen(
            st,
            settings=settings,
            catalog=catalog,
            lang=lang,
        )
        return
    if view == VIEW_GAME_SETTINGS:
        _render_game_settings_screen(
            st,
            settings=settings,
            catalog=catalog,
            lang=lang,
        )
        return
    if view == VIEW_HISTORY:
        if not database_available:
            st.warning(catalog.t(lang, "runtime.database_required"))
            return
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
            mutations_available=database_available and queue_available,
        )
        return

    if not database_available:
        st.warning(catalog.t(lang, "runtime.database_required"))
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
        render_app_error(st, exc, lang=lang)
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
        mutations_available=queue_available,
    )


def _render_pending_view_scroll(st: Any) -> None:
    """Reset scroll once after an intentional workspace transition."""
    if not consume_pending_view_scroll(st.session_state):
        return
    st.html(_VIEW_SCROLL_SCRIPT, unsafe_allow_javascript=True, width="content")


def _component_available(runtime_status: Any, component: str) -> bool:
    if runtime_status is None:
        return False
    return any(
        item.component == component and item.status == "available"
        for item in runtime_status.components
    )


def _streamlit() -> Any:
    return importlib.import_module("streamlit")


def _log_app_error(exc: AppError) -> None:
    """Record a top-level failure before the degraded shell explains it."""
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
