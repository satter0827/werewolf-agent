"""Administrator-only Streamlit workspace."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from werewolf_agent.adapters.factory import build_admin_client
from werewolf_agent.clients.presentation import implements_features
from werewolf_agent.clients.streamlit.i18n import I18nCatalog, Language
from werewolf_agent.clients.streamlit.screens import ScreenCatalog
from werewolf_agent.clients.streamlit.views.errors import render_app_error
from werewolf_agent.contracts import AppError
from werewolf_agent.settings import AppSettings


@implements_features(
    "admin_game_reveal",
    "admin_replay_verify",
    "admin_operation_get",
    "admin_llm_traces_get",
    "admin_llm_usage_get",
)
def _render_admin_screen(
    st: Any,
    *,
    settings: AppSettings,
    catalog: I18nCatalog,
    lang: Language,
    screens: ScreenCatalog,
) -> None:
    """Render admin operations without loading them through the normal game client."""
    st.title(catalog.t(lang, "admin.title"))
    st.caption(catalog.t(lang, "admin.caption"))
    game_id = st.text_input(catalog.t(lang, "admin.game_id"), key="admin_game_id")
    operation_id = st.text_input(catalog.t(lang, "admin.operation_id"), key="admin_operation_id")
    client = build_admin_client(settings)

    columns = st.columns(3)
    if columns[0].button(catalog.t(lang, "admin.reveal"), disabled=not game_id):
        _show(st, lambda: client.reveal_game(game_id), lang=lang)
    if columns[1].button(catalog.t(lang, "admin.replay_verify"), disabled=not game_id):
        _show(st, lambda: client.verify_replay(game_id), lang=lang)
    if columns[2].button(catalog.t(lang, "admin.operation_diagnostic"), disabled=not operation_id):
        _show(st, lambda: client.diagnose_operation(operation_id), lang=lang)

    with st.expander(
        catalog.t(lang, "admin.llm_analysis"),
        expanded=not screens.analysis_collapsed,
    ):
        if st.button(catalog.t(lang, "admin.llm_traces"), disabled=not game_id):
            _show(st, lambda: client.list_llm_traces(game_id), lang=lang)
        if st.button(catalog.t(lang, "admin.llm_usage"), disabled=not game_id):
            _show(st, lambda: client.get_llm_usage(game_id), lang=lang)


def _show(st: Any, loader: Callable[[], BaseModel], *, lang: Language) -> None:
    try:
        result = loader()
    except AppError as exc:
        render_app_error(st, exc, lang=lang)
        return
    st.json(result.model_dump(mode="json", exclude_none=True))


__all__ = ["_render_admin_screen"]
