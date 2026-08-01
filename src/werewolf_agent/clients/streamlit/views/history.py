"""Playable Streamlit interface for one manual player."""

from __future__ import annotations

import logging
from typing import Any

from werewolf_agent.clients.presentation import implements_features
from werewolf_agent.clients.streamlit.components import timeline_section_html
from werewolf_agent.clients.streamlit.i18n import (
    I18nCatalog,
    Language,
)
from werewolf_agent.clients.streamlit.operations import (
    list_recent_games,
    load_public_record,
)
from werewolf_agent.clients.streamlit.setup import VIEW_OBSERVE_SETUP, VIEW_PLAY_SETUP, switch_view
from werewolf_agent.clients.streamlit.view_models import timeline_items
from werewolf_agent.clients.streamlit.views.errors import render_app_error
from werewolf_agent.contracts import (
    AppError,
)
from werewolf_agent.settings import (
    AppSettings,
)

logger = logging.getLogger(__name__)
STREAMLIT_AUTH_SESSION_KEY = "_auth_session"


@implements_features("game_list", "game_get", "game_timeline_get")
def _render_history_screen(
    st: Any,
    *,
    settings: AppSettings,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    """Render personal game history and compact result analysis."""
    st.title(catalog.t(lang, "history.title"))
    st.caption(catalog.t(lang, "history.caption"))
    try:
        games = list_recent_games(settings=settings)
    except AppError as exc:
        render_app_error(st, exc, lang=lang)
        return
    if not games:
        st.info(catalog.t(lang, "history.empty"))
        actions = st.container(horizontal=True, key="records_empty_actions")
        if actions.button(catalog.t(lang, "history.start_play"), type="primary"):
            switch_view(st.session_state, VIEW_PLAY_SETUP)
            st.rerun()
        if actions.button(catalog.t(lang, "history.start_observe")):
            switch_view(st.session_state, VIEW_OBSERVE_SETUP)
            st.rerun()
        return

    game_numbers = {game.game_id: index for index, game in enumerate(games, start=1)}
    selected = st.selectbox(
        catalog.t(lang, "records.game"),
        games,
        format_func=lambda game: _record_label(
            game,
            index=game_numbers[game.game_id],
            catalog=catalog,
            lang=lang,
        ),
    )
    try:
        state, turns = load_public_record(settings=settings, game_id=selected.game_id)
    except AppError as exc:
        render_app_error(st, exc, lang=lang)
        return
    timeline = timeline_items(turns, state=state, catalog=catalog, lang=lang)
    st.markdown(
        timeline_section_html(
            timeline,
            variant="records",
            title=catalog.t(lang, "records.replay_title"),
            description=catalog.t(lang, "records.replay_description"),
            empty_text=catalog.t(lang, "game.timeline.empty"),
        ),
        unsafe_allow_html=True,
    )

    with st.expander(
        catalog.t(lang, "records.analysis"),
        expanded=False,
    ):
        _render_history_analysis(st, games=games, catalog=catalog, lang=lang)


def _record_label(
    game: Any,
    *,
    index: int,
    catalog: I18nCatalog,
    lang: Language,
) -> str:
    """Return a short localized record label without exposing an internal UUID."""
    return catalog.t(
        lang,
        "records.game_label",
        index=index,
        status=catalog.t(lang, f"status.{game.status}"),
        day=catalog.t(lang, "time.day", day=game.day),
    )


def _render_history_analysis(
    st: Any,
    *,
    games: list[Any],
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    """Render aggregate record analysis separately from the narrative replay."""
    completed = [game for game in games if game.status == "completed"]
    running = [game for game in games if game.status != "completed"]
    winner_counts: dict[str, int] = {}
    for game in completed:
        winner = game.winner or "-"
        winner_counts[winner] = winner_counts.get(winner, 0) + 1
    top_winner = max(winner_counts.items(), key=lambda item: item[1])[0] if winner_counts else "-"

    columns = st.columns(4)
    columns[0].metric(catalog.t(lang, "history.metric.total"), len(games))
    columns[1].metric(catalog.t(lang, "history.metric.completed"), len(completed))
    columns[2].metric(catalog.t(lang, "history.metric.running"), len(running))
    columns[3].metric(catalog.t(lang, "history.metric.top_winner"), top_winner)
    st.table(
        [
            {
                catalog.t(lang, "history.column.status"): catalog.label(
                    lang, "status", game.status
                ),
                catalog.t(lang, "history.column.day"): game.day,
                catalog.t(lang, "history.column.players"): game.player_count,
                catalog.t(lang, "history.column.winner"): catalog.label(
                    lang, "winner", game.winner
                ),
                catalog.t(lang, "history.column.updated"): game.updated_at.strftime("%H:%M:%S"),
            }
            for game in games
        ]
    )
