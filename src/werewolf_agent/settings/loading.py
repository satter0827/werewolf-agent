"""Packaged runtime defaultの読込み."""

from __future__ import annotations

import tomllib
from importlib.resources import files
from pathlib import Path

SETTINGS_PACKAGE = "werewolf_agent.settings.resources"
SETTINGS_FILE = "defaults.toml"


def load_packaged_defaults() -> dict[str, object]:
    """Packaged runtime defaultを返す."""
    resource = files(SETTINGS_PACKAGE).joinpath(SETTINGS_FILE)
    with resource.open("rb") as file:
        return tomllib.load(file)


def packaged_defaults_path() -> Path:
    """Return the installed packaged TOML path used by settings sources."""
    return Path(str(files(SETTINGS_PACKAGE).joinpath(SETTINGS_FILE)))


__all__ = ["load_packaged_defaults", "packaged_defaults_path"]
