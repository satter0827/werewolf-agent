"""formatting projections for the Streamlit game screen."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from werewolf_agent.clients.streamlit.i18n import I18nCatalog, Language
from werewolf_agent.clients.streamlit.view_models.types import (
    ScreenMode,
)
from werewolf_agent.contracts.schemas import (
    PublicPlayerState,
)
from werewolf_agent.settings.validation import (
    public_generated_player_label,
    public_generated_player_name_label,
)


def _player_name_map(players: list[PublicPlayerState]) -> dict[str, str]:
    return {player.id: _display_player_name(player.name, fallback=player.id) for player in players}


def _player_label(value: object, player_names: Mapping[str, str]) -> str:
    if value is None:
        return ""
    player_id = str(value)
    return player_names.get(player_id) or _public_actor_label(player_id) or player_id


def _player_list_label(value: object, player_names: Mapping[str, str]) -> str:
    if not isinstance(value, list):
        return ""
    return ", ".join(_player_label(item, player_names) for item in value if item is not None)


def _nested_text(payload: dict[str, Any], parent: str, child: str) -> str:
    value = payload.get(parent)
    if isinstance(value, dict):
        child_value = value.get(child)
        return str(child_value) if child_value is not None else ""
    return ""


def _time_text(value: datetime) -> str:
    return value.strftime("%H:%M:%S")


def _optional_time_text(value: datetime | None, catalog: I18nCatalog, lang: Language) -> str:
    return _time_text(value) if value is not None else catalog.t(lang, "game.updated.empty")


def _day_label(value: int, catalog: I18nCatalog, lang: Language) -> str:
    return catalog.t(lang, "time.day", day=value)


def _seconds_label(value: int | float, catalog: I18nCatalog, lang: Language) -> str:
    if value <= 0:
        return catalog.t(lang, "time.manual")
    seconds: int | str = int(value) if float(value).is_integer() else f"{value:.1f}"
    return catalog.t(lang, "time.seconds", seconds=seconds)


def _manual_player_label(
    players: list[PublicPlayerState],
    manual_player_id: str | None,
    screen_mode: ScreenMode,
    catalog: I18nCatalog,
    lang: Language,
) -> str:
    if screen_mode == "observer" or manual_player_id is None:
        return catalog.t(lang, "metric.player_observer")
    return _player_name(players, manual_player_id)


def _player_name(players: list[PublicPlayerState], player_id: object) -> str:
    player_id_text = str(player_id)
    for player in players:
        if player.id == player_id_text:
            return _display_player_name(player.name, fallback=player.id)
    return _public_actor_label(player_id_text) or player_id_text


def _display_player_name(name: str, *, fallback: str) -> str:
    stripped = name.strip()
    return (
        public_generated_player_name_label(stripped)
        or stripped
        or _public_actor_label(fallback)
        or fallback
    )


def _public_actor_label(actor_id: str) -> str:
    if not actor_id:
        return ""
    return public_generated_player_label(actor_id) or actor_id
