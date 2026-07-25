"""History selector models for the Streamlit interface."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import uuid4

from werewolf_agent.clients.streamlit.constants import DEFAULT_NARRATION_MODE
from werewolf_agent.clients.streamlit.i18n import I18nCatalog, Language
from werewolf_agent.clients.streamlit.view_models import (
    SavedGameOptionView,
    ScreenMode,
)
from werewolf_agent.contracts.schemas import (
    GAME_STATUS_COMPLETED,
    GAME_STATUS_RUNNING,
    CustomCharacterDefinitionRequest,
    CustomRoleDefinitionRequest,
    GameResponse,
    LocalRulesSettings,
    NarrationMode,
    PublicGameSummary,
)


@dataclass(frozen=True)
class SessionGameSelection:
    """One playable game selection held only in the current Streamlit session."""

    selection_id: str
    game_id: str
    manual_player_id: str | None
    role_counts: dict[str, int]
    rules: LocalRulesSettings
    seed: int | None
    scenario_id: str | None
    setup_preset_id: str | None
    agent_strategy_id: str | None
    narration_mode: NarrationMode
    character_assignments: dict[str, str]
    custom_roles: list[CustomRoleDefinitionRequest]
    custom_characters: list[CustomCharacterDefinitionRequest]


def create_session_game_selection(
    response: GameResponse,
    *,
    manual_player_id: str | None,
    role_counts: Mapping[str, int],
    rules: LocalRulesSettings,
    seed: int | None,
    scenario_id: str | None,
    setup_preset_id: str | None,
    agent_strategy_id: str | None,
    narration_mode: NarrationMode,
    character_assignments: Mapping[str, str],
    custom_roles: list[CustomRoleDefinitionRequest],
    custom_characters: list[CustomCharacterDefinitionRequest],
) -> SessionGameSelection:
    """Create a session-only playable selection from a newly created game."""
    return SessionGameSelection(
        selection_id=uuid4().hex,
        game_id=response.game_id,
        manual_player_id=manual_player_id,
        role_counts={str(role_id): int(count) for role_id, count in role_counts.items()},
        rules=rules,
        seed=seed,
        scenario_id=scenario_id,
        setup_preset_id=setup_preset_id,
        agent_strategy_id=agent_strategy_id,
        narration_mode=narration_mode,
        character_assignments={
            str(player_id): str(character_id)
            for player_id, character_id in character_assignments.items()
        },
        custom_roles=list(custom_roles),
        custom_characters=list(custom_characters),
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
        player_count = (
            game.player_count if game is not None else sum(session_selection.role_counts.values())
        )
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
                role_counts=dict(session_selection.role_counts),
                rules=session_selection.rules,
                seed=session_selection.seed,
                scenario_id=session_selection.scenario_id,
                setup_preset_id=session_selection.setup_preset_id,
                agent_strategy_id=session_selection.agent_strategy_id,
                narration_mode=session_selection.narration_mode,
                character_assignments=dict(session_selection.character_assignments),
                custom_roles=list(session_selection.custom_roles),
                custom_characters=list(session_selection.custom_characters),
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
                narration_mode=cast(NarrationMode, DEFAULT_NARRATION_MODE),
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
