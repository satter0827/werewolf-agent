"""Packaged runtime defaultの読込み."""

from __future__ import annotations

import tomllib
from importlib.resources import files

SETTINGS_PACKAGE = "werewolf_agent.settings.resources"
SETTINGS_FILE = "defaults.toml"


def load_packaged_defaults() -> dict[str, object]:
    """Packaged runtime defaultを返す."""
    resource = files(SETTINGS_PACKAGE).joinpath(SETTINGS_FILE)
    with resource.open("rb") as file:
        return tomllib.load(file)


__all__ = ["load_packaged_defaults"]
