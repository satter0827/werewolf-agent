"""Redaction helpers for logs and replay events."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

from werewolf_agent.security.constants import (
    REDACTED,
    REDACTION_NORMALIZED_SEPARATOR,
    REDACTION_SOURCE_SEPARATOR,
    SENSITIVE_KEY_PARTS,
)

_SENSITIVE_ASSIGNMENT_PATTERN: Final = re.compile(
    r"(?i)\b(secret|token|api[_-]?key|apikey|authorization|password|"
    r"night_action|private_state|role|target|target_id)"
    r"(\s*[:=]\s*)((?:Bearer\s+)?[^,\s;]+)"
)
_URI_CREDENTIALS_PATTERN: Final = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^/\s:@]+):([^@\s/]+)@")


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
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_text(value: str) -> str:
    """Mask common sensitive key assignments inside free-form log strings."""
    redacted = _SENSITIVE_ASSIGNMENT_PATTERN.sub(r"\1\2[REDACTED]", value)
    return _URI_CREDENTIALS_PATTERN.sub(r"\1[REDACTED]@", redacted)


def is_sensitive_key(key: str) -> bool:
    """Return whether a structured field name should be masked."""
    normalized = key.lower().replace(REDACTION_SOURCE_SEPARATOR, REDACTION_NORMALIZED_SEPARATOR)
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)
