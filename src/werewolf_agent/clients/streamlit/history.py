"""History selector models for the Streamlit interface."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from werewolf_agent.clients.streamlit.i18n import I18nCatalog, Language
from werewolf_agent.clients.streamlit.view_models import (
    SavedGameOptionView,
    ScreenMode,
)
from werewolf_agent.contracts.schemas import (
    GAME_STATUS_COMPLETED,
    GAME_STATUS_RUNNING,
    DeliberationLevel,
    GameResponse,
    PublicGameSummary,
)


@dataclass(frozen=True)
class SessionGameSelection:
    """One playable game selection held only in the current Streamlit session."""

    selection_id: str
    game_id: str
    manual_player_id: str | None
    player_count: int
    seed: int | None
    deliberation_level: DeliberationLevel


def create_session_game_selection(
    response: GameResponse,
    *,
    manual_player_id: str | None,
    seed: int | None,
    player_count: int,
    deliberation_level: DeliberationLevel = "standard",
) -> SessionGameSelection:
    """Create a session-only playable selection from a newly created game."""
    return SessionGameSelection(
        selection_id=uuid4().hex,
        game_id=response.game_id,
        manual_player_id=manual_player_id,
        player_count=player_count,
        seed=seed,
        deliberation_level=deliberation_level,
    )


def build_history_options(
    session_selection: SessionGameSelection | None,
    games: list[PublicGameSummary],
    *,
    catalog: I18nCatalog,
    lang: Language,
) -> list[SavedGameOptionView]:
    """Return history-selector options without local save-file persistence."""
    options: list[SavedGameOptionView] = []
    games_by_id = {game.game_id: game for game in games}
    session_game_id = ""
    if session_selection is not None:
        game = games_by_id.get(session_selection.game_id)
        status = game.status if game is not None else GAME_STATUS_RUNNING
        day = game.day if game is not None else 1
        player_count = game.player_count if game is not None else session_selection.player_count
        updated_at = game.updated_at if game is not None else None
        mode: ScreenMode = "playable" if session_selection.manual_player_id else "observer"
        options.append(
            SavedGameOptionView(
                option_id=f"session:{session_selection.selection_id}",
                label=_option_label(
                    prefix=catalog.t(lang, "history.prefix.session"),
                    status=status,
                    day=day,
                    player_count=player_count,
                    updated_at=updated_at,
                    mode_label=catalog.t(lang, "setup.mode.play")
                    if session_selection.manual_player_id
                    else catalog.t(lang, "setup.mode.observe"),
                    catalog=catalog,
                    lang=lang,
                ),
                game_id=session_selection.game_id,
                mode=mode,
                manual_player_id=session_selection.manual_player_id,
                seed=session_selection.seed,
                deliberation_level=session_selection.deliberation_level,
            )
        )
        session_game_id = session_selection.game_id

    for index, game in enumerate(
        [game for game in games if game.game_id != session_game_id],
        start=1,
    ):
        options.append(
            SavedGameOptionView(
                option_id=f"game:{game.game_id}",
                label=_option_label(
                    prefix=catalog.t(lang, "history.prefix.game", index=index),
                    status=game.status,
                    day=game.day,
                    player_count=game.player_count,
                    updated_at=game.updated_at,
                    mode_label=catalog.t(lang, "setup.mode.observe"),
                    catalog=catalog,
                    lang=lang,
                ),
                game_id=game.game_id,
                mode="observer",
                seed=game.seed,
            )
        )
    return options


def _option_label(
    *,
    prefix: str,
    status: str,
    day: int,
    player_count: int,
    updated_at: datetime | None,
    mode_label: str,
    catalog: I18nCatalog,
    lang: Language,
) -> str:
    status_label = (
        catalog.t(lang, "status.completed")
        if status == GAME_STATUS_COMPLETED
        else catalog.t(lang, "status.running")
    )
    updated_label = updated_at.strftime("%H:%M") if updated_at is not None else "-"
    return (
        f"{prefix} / {status_label} / {catalog.t(lang, 'time.day', day=day)} / "
        f"{player_count} / "
        f"{catalog.t(lang, 'metric.updated')} {updated_label} / {mode_label}"
    )
