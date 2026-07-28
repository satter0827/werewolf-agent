"""Browser journey、状態、deviceの実行catalog。"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import cast

CATALOG_PATH = Path(__file__).with_name("catalog.toml")


def load_catalog() -> dict[str, dict[str, object]]:
    """検証済みBrowser catalogを返す。"""
    with CATALOG_PATH.open("rb") as stream:
        document = tomllib.load(stream)
    for section in ("journeys", "states", "devices", "captures"):
        if not isinstance(document.get(section), dict) or not document[section]:
            raise ValueError(f"Browser catalogの{section}を定義してください。")
    catalog = {
        section: document[section] for section in ("journeys", "states", "devices", "captures")
    }
    _validate_catalog(catalog)
    return catalog


def _validate_catalog(catalog: dict[str, dict[str, object]]) -> None:
    """Catalog全項目の型と相互参照を選択前に検証する。"""
    scenario_names: set[str] = set()
    for section in ("journeys", "states"):
        for name, entries in catalog[section].items():
            if (
                not isinstance(entries, list)
                or not entries
                or not all(isinstance(entry, str) and entry for entry in entries)
            ):
                raise ValueError(f"Browser catalogの{section}.{name}が不正です。")
            scenario_names.update(entries)
    if not all(
        isinstance(name, str) and isinstance(value, str) and value
        for name, value in catalog["devices"].items()
    ):
        raise ValueError("Browser catalogのdevicesが不正です。")
    known_devices = set(catalog["devices"])
    for name, value in catalog["captures"].items():
        if not isinstance(value, dict):
            raise ValueError(f"Browser catalogのcaptures.{name}が不正です。")
        scenario = value.get("scenario")
        filename = value.get("filename")
        devices = value.get("devices", list(known_devices))
        if scenario not in scenario_names:
            raise ValueError(f"Browser captureのscenarioが未登録です: {name}")
        if not isinstance(filename, str) or not filename.endswith(".png"):
            raise ValueError(f"Browser captureのfilenameが不正です: {name}")
        if (
            not isinstance(devices, list)
            or not devices
            or not all(isinstance(device, str) and device in known_devices for device in devices)
        ):
            raise ValueError(f"Browser captureのdevicesが不正です: {name}")


def scenario_expression(
    journey: str | None,
    state: str | None,
    captures: tuple[str, ...] = (),
) -> str | None:
    """Journeyと状態の積集合をpytest式へ変換する。"""
    catalog = load_catalog()
    selected: set[str] | None = None
    for section, value in (("journeys", journey), ("states", state)):
        if value is None:
            continue
        entries = catalog[section].get(value)
        if not isinstance(entries, list) or not all(isinstance(item, str) for item in entries):
            raise ValueError(f"未定義のBrowser {section[:-1]}です: {value}")
        names = set(entries)
        selected = names if selected is None else selected & names
    if captures:
        capture_scenarios = {cast(str, _capture_definition(name)["scenario"]) for name in captures}
        selected = capture_scenarios if selected is None else selected & capture_scenarios
    if selected == set():
        raise ValueError("指定したjourneyとstateに対応するscenarioがありません。")
    return " or ".join(sorted(selected)) if selected else None


def capture_filenames(captures: tuple[str, ...], devices: tuple[str, ...]) -> tuple[str, ...]:
    """論理capture名を選択device向けの実filenameへ変換する。"""
    catalog = load_catalog()
    unknown_devices = sorted(set(devices) - set(catalog["devices"]))
    if unknown_devices:
        raise ValueError(f"未定義のBrowser deviceです: {', '.join(unknown_devices)}")
    filenames: set[str] = set()
    for capture in captures:
        definition = _capture_definition(capture)
        supported = definition.get("devices", devices)
        if not isinstance(supported, list | tuple) or not all(
            isinstance(device, str) for device in supported
        ):
            raise ValueError(f"Browser captureのdevicesが不正です: {capture}")
        selected_devices = [device for device in devices if device in supported]
        if not selected_devices:
            raise ValueError(f"capture {capture}は指定deviceに対応していません。")
        filename = cast(str, definition["filename"])
        if "{device}" in filename:
            filenames.update(filename.format(device=device) for device in selected_devices)
        else:
            filenames.add(filename)
    return tuple(sorted(filenames))


def _capture_definition(name: str) -> dict[str, object]:
    definition = load_catalog()["captures"].get(name)
    if (
        not isinstance(definition, dict)
        or not isinstance(definition.get("scenario"), str)
        or not isinstance(definition.get("filename"), str)
    ):
        raise ValueError(f"未定義のBrowser captureです: {name}")
    return definition


__all__ = ["capture_filenames", "load_catalog", "scenario_expression"]
