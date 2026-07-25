"""Playable Streamlit interface for one manual player."""

from __future__ import annotations

import logging
from typing import Any

from werewolf_agent.clients.streamlit.i18n import (
    I18nCatalog,
    Language,
)
from werewolf_agent.clients.streamlit.operations import (
    list_recent_games,
)
from werewolf_agent.contracts import (
    AppError,
)
from werewolf_agent.settings import (
    AppSettings,
)

logger = logging.getLogger(__name__)
STREAMLIT_AUTH_SESSION_KEY = "_auth_session"


def _render_history_screen(
    st: Any,
    *,
    settings: AppSettings,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    """Render personal game history and compact result analysis."""
    st.header(catalog.t(lang, "history.title"))
    st.caption(catalog.t(lang, "settings.mode.supabase"))
    try:
        games = list_recent_games(settings=settings)
    except AppError as exc:
        st.error(exc.detail)
        return
    if not games:
        st.info(catalog.t(lang, "history.empty"))
        return

    completed = [game for game in games if game.status == "completed"]
    running = [game for game in games if game.status != "completed"]
    winner_counts: dict[str, int] = {}
    for game in completed:
        winner = game.winner or "-"
        winner_counts[winner] = winner_counts.get(winner, 0) + 1
    top_winner = "-"
    if winner_counts:
        top_winner = max(winner_counts.items(), key=lambda item: item[1])[0]

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
