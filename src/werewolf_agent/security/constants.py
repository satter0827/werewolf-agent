"""security constantsが所有する安定した値."""

from __future__ import annotations

from typing import Final

REDACTED: Final = "[REDACTED]"

REDACTION_SOURCE_SEPARATOR: Final = "-"

REDACTION_NORMALIZED_SEPARATOR: Final = "_"

SENSITIVE_KEY_PARTS: Final = (
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "known_roles",
    "night_action",
    "password",
    "private_state",
    "raw_response",
    "role",
)
