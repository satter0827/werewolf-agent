"""Local save-slot storage for the Streamlit play screen."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from werewolf_agent.contracts.schemas import (
    GameRunResponse,
    LocalRulesSettings,
    PublicGameRunSummary,
    PublicGameState,
)
from werewolf_agent.interface.entrypoint.streamlit.i18n import I18nCatalog, Language
from werewolf_agent.interface.entrypoint.streamlit.view_models import (
    SavedGameOptionView,
    ScreenMode,
)

SAVE_FILE_VERSION = 3


@dataclass(frozen=True)
class SaveSlot:
    """One locally managed playable save slot."""

    slot_id: str
    game_id: str
    human_player_id: str | None
    role_counts: dict[str, int]
    rules: LocalRulesSettings
    seed: int | None
    status: str
    phase: str
    day: int
    player_count: int
    alive_count: int
    created_at: datetime | None
    updated_at: datetime | None

    def with_state(self, state: PublicGameState) -> SaveSlot:
        """Return this slot refreshed with the latest public game metadata."""
        return SaveSlot(
            slot_id=self.slot_id,
            game_id=self.game_id,
            human_player_id=self.human_player_id,
            role_counts=dict(self.role_counts),
            rules=self.rules,
            seed=self.seed,
            status=state.status,
            phase=state.phase,
            day=state.day,
            player_count=len(state.players),
            alive_count=len(state.alive_player_ids),
            created_at=state.created_at or self.created_at,
            updated_at=state.updated_at or self.updated_at,
        )


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
    return sorted(
        [slot for slot in slots if slot is not None],
        key=lambda slot: slot.updated_at or slot.created_at or datetime.min,
        reverse=True,
    )


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
    response: GameRunResponse,
    *,
    human_player_id: str | None,
    role_counts: Mapping[str, int],
    rules: LocalRulesSettings,
    seed: int | None,
) -> SaveSlot:
    """Create a playable save slot from a newly created game response."""
    state = response.state
    return SaveSlot(
        slot_id=uuid4().hex,
        game_id=response.game_id,
        human_player_id=human_player_id,
        role_counts={str(role_id): int(count) for role_id, count in role_counts.items()},
        rules=rules,
        seed=seed,
        status=state.status,
        phase=state.phase,
        day=state.day,
        player_count=len(state.players),
        alive_count=len(state.alive_player_ids),
        created_at=state.created_at,
        updated_at=state.updated_at,
    )


def build_saved_game_options(
    slots: list[SaveSlot],
    runs: list[PublicGameRunSummary],
    *,
    catalog: I18nCatalog,
    lang: Language,
    control_tokens: Mapping[str, str] | None = None,
) -> list[SavedGameOptionView]:
    """Return save-selector options without exposing internal ids in labels."""
    options: list[SavedGameOptionView] = []
    runs_by_game = {run.game_id: run for run in runs}
    saved_game_ids = {slot.game_id for slot in slots}
    control_tokens_by_slot = control_tokens or {}
    for index, slot in enumerate(slots, start=1):
        run = runs_by_game.get(slot.game_id)
        status = run.status if run is not None else slot.status
        day = run.day if run is not None else slot.day
        player_count = run.player_count if run is not None else slot.player_count
        updated_at = run.updated_at if run is not None else slot.updated_at
        control_token = control_tokens_by_slot.get(slot.slot_id, "")
        mode: ScreenMode = "playable" if control_token else "observer"
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
                    if control_token
                    else catalog.t(lang, "setup.mode.observe"),
                    catalog=catalog,
                    lang=lang,
                ),
                game_id=slot.game_id,
                mode=mode,
                human_player_id=slot.human_player_id if control_token else None,
                control_token=control_token,
                role_counts=dict(slot.role_counts),
                rules=slot.rules,
                seed=slot.seed,
            )
        )
    observer_runs = [run for run in runs if run.game_id not in saved_game_ids]
    for index, run in enumerate(observer_runs, start=1):
        options.append(
            SavedGameOptionView(
                option_id=f"run:{run.game_id}",
                label=_option_label(
                    prefix=catalog.t(lang, "save.prefix.observer", index=index),
                    status=run.status,
                    day=run.day,
                    player_count=run.player_count,
                    updated_at=run.updated_at,
                    mode_label=catalog.t(lang, "setup.mode.observe"),
                    catalog=catalog,
                    lang=lang,
                ),
                game_id=run.game_id,
                mode="observer",
                seed=run.seed,
            )
        )
    return options


def _slot_from_dict(payload: dict[str, object]) -> SaveSlot | None:
    try:
        return SaveSlot(
            slot_id=_required_text(payload, "slot_id"),
            game_id=_required_text(payload, "game_id"),
            human_player_id=_optional_text(payload.get("human_player_id")),
            role_counts=_role_counts(payload.get("role_counts")),
            rules=LocalRulesSettings.model_validate(payload["rules"]),
            seed=_optional_int(payload.get("seed")),
            status=_required_text(payload, "status"),
            phase=_required_text(payload, "phase"),
            day=_required_int(payload, "day"),
            player_count=_required_int(payload, "player_count"),
            alive_count=_required_int(payload, "alive_count"),
            created_at=_optional_datetime(payload.get("created_at")),
            updated_at=_optional_datetime(payload.get("updated_at")),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _slot_to_dict(slot: SaveSlot) -> dict[str, object]:
    return {
        "slot_id": slot.slot_id,
        "game_id": slot.game_id,
        "human_player_id": slot.human_player_id,
        "role_counts": dict(slot.role_counts),
        "rules": slot.rules.model_dump(mode="json"),
        "seed": slot.seed,
        "status": slot.status,
        "phase": slot.phase,
        "day": slot.day,
        "player_count": slot.player_count,
        "alive_count": slot.alive_count,
        "created_at": _datetime_text(slot.created_at),
        "updated_at": _datetime_text(slot.updated_at),
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


def _required_int(payload: dict[str, object], key: str) -> int:
    value = payload[key]
    if isinstance(value, (str, bytes, bytearray)):
        return int(value)
    if isinstance(value, int):
        return value
    raise ValueError(f"{key} must be an integer")


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


def _optional_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    return datetime.fromisoformat(str(value))


def _datetime_text(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


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
