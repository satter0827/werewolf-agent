"""Streamlit client-owned packaged resources."""

from __future__ import annotations

import tomllib
from importlib.resources import files
from pathlib import Path

PACKAGE = "werewolf_agent.clients.streamlit.resources"
I18N_FILE = "i18n.toml"
CSS_FILES = (
    "tokens.css",
    "base.css",
    "layout.css",
    "components.css",
    "streamlit.css",
    "responsive.css",
)


def load_i18n_payload(path: Path | None) -> tuple[dict[str, object], bool]:
    """Load translations and report whether an external override was rejected."""
    if path is not None:
        try:
            with path.open("rb") as file:
                return tomllib.load(file), False
        except (OSError, tomllib.TOMLDecodeError):
            return _load_packaged_toml(I18N_FILE), True
    return _load_packaged_toml(I18N_FILE), False


def load_packaged_i18n() -> dict[str, object]:
    """Load the trusted packaged translation catalog."""
    return _load_packaged_toml(I18N_FILE)


def load_css() -> str:
    """Load the trusted packaged stylesheet in dependency order."""
    return "\n".join(
        files(PACKAGE).joinpath(name).read_text(encoding="utf-8") for name in CSS_FILES
    )


def _load_packaged_toml(name: str) -> dict[str, object]:
    resource = files(PACKAGE).joinpath(name)
    with resource.open("rb") as file:
        return tomllib.load(file)


__all__ = ["load_css", "load_i18n_payload", "load_packaged_i18n"]
