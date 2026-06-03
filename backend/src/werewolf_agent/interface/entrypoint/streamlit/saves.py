"""Local save-slot storage for the Streamlit play screen."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from werewolf_agent.contracts.schemas import (
    CustomCharacterDefinitionRequest,
    CustomRoleDefinitionRequest,
    GameResponse,
    LocalRulesSettings,
    NarrationMode,
    PublicGameSummary,
)
from werewolf_agent.interface.entrypoint.streamlit.i18n import I18nCatalog, Language
from werewolf_agent.interface.entrypoint.streamlit.view_models import (
    SavedGameOptionView,
    ScreenMode,
)

SAVE_FILE_VERSION = 6


@dataclass(frozen=True)
class SaveSlot:
    """One locally managed playable save slot."""

    slot_id: str
    game_id: str
    manual_player_id: str | None
    role_counts: dict[str, int]
    rules: LocalRulesSettings
    seed: int | None
    scenario_id: str | None
    setup_preset_id: str | None
    narration_mode: NarrationMode
    character_assignments: dict[str, str]
    custom_roles: list[CustomRoleDefinitionRequest]
    custom_characters: list[CustomCharacterDefinitionRequest]


def load_save_slots(save_file: Path) -> list[SaveSlot]:
    """Load current save slots, returning an empty list for invalid files."""
    if not save_file.exists():
        return []
    try:
        payload = json.loads(save_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return []
    if not isinstance(payload, dict):
        return []
    if payload.get("version") != SAVE_FILE_VERSION:
        return []
    raw_slots = payload.get("slots")
    if not isinstance(raw_slots, list):
        return []
    slots = [_slot_from_dict(item) for item in raw_slots if isinstance(item, dict)]
    return [slot for slot in slots if slot is not None]


def write_save_slots(save_file: Path, slots: list[SaveSlot]) -> None:
    """Write save slots in the current format."""
    save_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": SAVE_FILE_VERSION,
        "slots": [_slot_to_dict(slot) for slot in slots],
    }
    save_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def upsert_save_slot(save_file: Path, slot: SaveSlot) -> None:
    """Insert or replace one save slot."""
    slots = [
        existing for existing in load_save_slots(save_file) if existing.slot_id != slot.slot_id
    ]
    slots.insert(0, slot)
    write_save_slots(save_file, slots)


def create_save_slot(
    response: GameResponse,
    *,
    manual_player_id: str | None,
    role_counts: Mapping[str, int],
    rules: LocalRulesSettings,
    seed: int | None,
    scenario_id: str | None,
    setup_preset_id: str | None,
    narration_mode: NarrationMode,
    character_assignments: Mapping[str, str],
    custom_roles: list[CustomRoleDefinitionRequest],
    custom_characters: list[CustomCharacterDefinitionRequest],
) -> SaveSlot:
    """Create a playable save slot from a newly created game response."""
    return SaveSlot(
        slot_id=uuid4().hex,
        game_id=response.game_id,
        manual_player_id=manual_player_id,
        role_counts={str(role_id): int(count) for role_id, count in role_counts.items()},
        rules=rules,
        seed=seed,
        scenario_id=scenario_id,
        setup_preset_id=setup_preset_id,
        narration_mode=narration_mode,
        character_assignments={
            str(player_id): str(character_id)
            for player_id, character_id in character_assignments.items()
        },
        custom_roles=list(custom_roles),
        custom_characters=list(custom_characters),
    )


def build_saved_game_options(
    slots: list[SaveSlot],
    games: list[PublicGameSummary],
    *,
    catalog: I18nCatalog,
    lang: Language,
    manual_player_tokens: Mapping[str, str] | None = None,
) -> list[SavedGameOptionView]:
    """Return save-selector options without exposing internal ids in labels."""
    options: list[SavedGameOptionView] = []
    games_by_id = {game.game_id: game for game in games}
    saved_game_ids = {slot.game_id for slot in slots}
    manual_player_tokens_by_slot = manual_player_tokens or {}
    for index, slot in enumerate(slots, start=1):
        game = games_by_id.get(slot.game_id)
        status = game.status if game is not None else "running"
        day = game.day if game is not None else 1
        player_count = game.player_count if game is not None else sum(slot.role_counts.values())
        updated_at = game.updated_at if game is not None else None
        manual_token = manual_player_tokens_by_slot.get(slot.slot_id, "")
        mode: ScreenMode = "playable" if manual_token else "observer"
        options.append(
            SavedGameOptionView(
                option_id=f"slot:{slot.slot_id}",
                label=_option_label(
                    prefix=catalog.t(lang, "save.prefix.slot", index=index),
                    status=status,
                    day=day,
                    player_count=player_count,
                    updated_at=updated_at,
                    mode_label=catalog.t(lang, "setup.mode.play")
                    if manual_token
                    else catalog.t(lang, "setup.mode.observe"),
                    catalog=catalog,
                    lang=lang,
                ),
                game_id=slot.game_id,
                mode=mode,
                manual_player_id=slot.manual_player_id if manual_token else None,
                manual_token=manual_token,
                role_counts=dict(slot.role_counts),
                rules=slot.rules,
                seed=slot.seed,
                scenario_id=slot.scenario_id,
                setup_preset_id=slot.setup_preset_id,
                narration_mode=slot.narration_mode,
                character_assignments=dict(slot.character_assignments),
                custom_roles=list(slot.custom_roles),
                custom_characters=list(slot.custom_characters),
            )
        )
    observer_games = [game for game in games if game.game_id not in saved_game_ids]
    for index, game in enumerate(observer_games, start=1):
        options.append(
            SavedGameOptionView(
                option_id=f"game:{game.game_id}",
                label=_option_label(
                    prefix=catalog.t(lang, "save.prefix.observer", index=index),
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
                narration_mode="standard",
            )
        )
    return options


def _slot_from_dict(payload: dict[str, object]) -> SaveSlot | None:
    try:
        if "manual_token" in payload:
            raise ValueError("save slot must not contain manual_token")
        return SaveSlot(
            slot_id=_required_text(payload, "slot_id"),
            game_id=_required_text(payload, "game_id"),
            manual_player_id=_optional_text(payload.get("manual_player_id")),
            role_counts=_role_counts(payload.get("role_counts")),
            rules=LocalRulesSettings.model_validate(payload["rules"]),
            seed=_optional_int(payload.get("seed")),
            scenario_id=_optional_text(payload.get("scenario_id")),
            setup_preset_id=_optional_text(payload.get("setup_preset_id")),
            narration_mode=_narration_mode(payload.get("narration_mode")),
            character_assignments=_text_map(payload.get("character_assignments")),
            custom_roles=_custom_roles(payload.get("custom_roles")),
            custom_characters=_custom_characters(payload.get("custom_characters")),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _slot_to_dict(slot: SaveSlot) -> dict[str, object]:
    return {
        "slot_id": slot.slot_id,
        "game_id": slot.game_id,
        "manual_player_id": slot.manual_player_id,
        "role_counts": dict(slot.role_counts),
        "rules": slot.rules.model_dump(mode="json"),
        "seed": slot.seed,
        "scenario_id": slot.scenario_id,
        "setup_preset_id": slot.setup_preset_id,
        "narration_mode": slot.narration_mode,
        "character_assignments": dict(slot.character_assignments),
        "custom_roles": [item.model_dump(mode="json") for item in slot.custom_roles],
        "custom_characters": [item.model_dump(mode="json") for item in slot.custom_characters],
    }


def _required_text(payload: dict[str, object], key: str) -> str:
    value = payload[key]
    text = str(value).strip()
    if not text:
        raise ValueError(f"{key} must be non-empty")
    return text


def _optional_text(value: object) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, int):
        return value
    return int(str(value))


def _role_counts(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError("role_counts must be an object")
    return {str(role_id): int(count) for role_id, count in value.items()}


def _text_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): str(item) for key, item in value.items() if str(key).strip() and str(item).strip()
    }


def _narration_mode(value: object) -> NarrationMode:
    text = str(value or "standard").strip()
    if text in {"none", "standard", "rich"}:
        return cast(NarrationMode, text)
    return "standard"


def _custom_roles(value: object) -> list[CustomRoleDefinitionRequest]:
    if not isinstance(value, list):
        return []
    roles: list[CustomRoleDefinitionRequest] = []
    for item in value:
        if isinstance(item, dict):
            roles.append(CustomRoleDefinitionRequest.model_validate(item))
    return roles


def _custom_characters(value: object) -> list[CustomCharacterDefinitionRequest]:
    if not isinstance(value, list):
        return []
    characters: list[CustomCharacterDefinitionRequest] = []
    for item in value:
        if isinstance(item, dict):
            characters.append(CustomCharacterDefinitionRequest.model_validate(item))
    return characters


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
        if status == "completed"
        else catalog.t(lang, "status.running")
    )
    updated_label = updated_at.strftime("%H:%M") if updated_at is not None else "-"
    return (
        f"{prefix} / {status_label} / {catalog.t(lang, 'time.day', day=day)} / "
        f"{player_count} / "
        f"{catalog.t(lang, 'metric.updated')} {updated_label} / {mode_label}"
    )
