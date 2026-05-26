"""Shared redaction helpers for logs and replay events."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

REDACTED: Final = "[REDACTED]"
SENSITIVE_KEY_PARTS: Final = (
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "password",
)


def redact_mapping(mapping: Mapping[str, object]) -> dict[str, object]:
    """Return a recursively redacted copy of a mapping."""
    return {str(key): redact_value(str(key), value) for key, value in mapping.items()}


def redact_value(key: str | None, value: object) -> object:
    """Return a recursively redacted value when its key is sensitive."""
    if key is not None and is_sensitive_key(key):
        return REDACTED
    if isinstance(value, Mapping):
        return {
            str(item_key): redact_value(str(item_key), item_value)
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact_value(None, item) for item in value]
    return value


def is_sensitive_key(key: str) -> bool:
    """Return whether a structured field name should be masked."""
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)
