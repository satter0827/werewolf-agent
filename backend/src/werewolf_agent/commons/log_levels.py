"""Logging level helpers for entry point adapters."""

from __future__ import annotations

import logging


def log_level_number(level: str) -> int:
    """Return a stdlib logging level number for a configured level name."""
    resolved = logging.getLevelName(level.upper())
    return resolved if isinstance(resolved, int) else logging.INFO
