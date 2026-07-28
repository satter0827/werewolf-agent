"""Helpers for keeping private identifiers out of operational logs."""

from __future__ import annotations

import re
from typing import Final

_GAME_ID_PATH_PATTERN: Final = re.compile(r"(?P<prefix>(?:^|/)games/)[^/?#]+")
_PLAYER_ID_PATH_PATTERN: Final = re.compile(r"(?P<prefix>(?:^|/)players/)[^/?#]+")


def safe_http_log_path(path: str) -> str:
    """Return an HTTP path template suitable for operational logs."""
    safe_path = _GAME_ID_PATH_PATTERN.sub(r"\g<prefix>{game_id}", path)
    return _PLAYER_ID_PATH_PATTERN.sub(r"\g<prefix>{player_id}", safe_path)
