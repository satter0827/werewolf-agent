"""Redaction helpers for logs and replay events."""

from __future__ import annotations

import json
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
    r"(?i)(?<![A-Za-z0-9_-])([\"']?)(secret|token|api[_-]?key|apikey|authorization|password|"
    r"night_action|private_state|role|target|target_id)"
    r"\1(\s*[:=]\s*)((?:Bearer\s+)?(?:[\"'][^\"']*[\"']|[^,\s;]+))"
)
_SENSITIVE_JSON_KEY_PATTERN: Final = re.compile(
    r'(?i)(")((?:secret|token|api[_-]?key|apikey|authorization|password|'
    r"night_action|private_state|role|target|target_id))\1(\s*:\s*)"
)
_URI_CREDENTIALS_PATTERN: Final = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^/\s:@]+):([^@\s/]+)@")
_JSON_DECODER: Final = json.JSONDecoder()
_JSON_NESTING_LIMIT: Final = 256


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
    redacted_json = _redact_json_assignments(value)
    redacted = _SENSITIVE_ASSIGNMENT_PATTERN.sub(_redact_assignment, redacted_json)
    return _URI_CREDENTIALS_PATTERN.sub(r"\1[REDACTED]@", redacted)


def _redact_json_assignments(value: str) -> str:
    """Mask a complete JSON value after each sensitive quoted key."""
    output: list[str] = []
    copied_until = 0
    search_from = 0
    while match := _SENSITIVE_JSON_KEY_PATTERN.search(value, search_from):
        if _json_value_exceeds_nesting_limit(value, match.end()):
            output.append(value[copied_until : match.end()])
            output.append(json.dumps(REDACTED, ensure_ascii=False))
            return "".join(output)
        try:
            _decoded, value_end = _JSON_DECODER.raw_decode(value, match.end())
        except RecursionError:
            output.append(value[copied_until : match.end()])
            output.append(json.dumps(REDACTED, ensure_ascii=False))
            return "".join(output)
        except json.JSONDecodeError:
            search_from = match.end()
            continue
        output.append(value[copied_until : match.end()])
        output.append(json.dumps(REDACTED, ensure_ascii=False))
        copied_until = value_end
        search_from = value_end
    output.append(value[copied_until:])
    return "".join(output)


def _json_value_exceeds_nesting_limit(value: str, start: int) -> bool:
    """Detect excessive JSON nesting consistently across Python versions."""
    depth = 0
    in_string = False
    escaped = False
    for character in value[start:]:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > _JSON_NESTING_LIMIT:
                return True
        elif character in "]}":
            if depth == 0:
                return False
            depth -= 1
            if depth == 0:
                return False
        elif depth == 0 and not character.isspace():
            return False
    return False


def _redact_assignment(match: re.Match[str]) -> str:
    """Preserve assignment syntax while replacing only the sensitive value."""
    key_quote = match.group(1)
    raw_value = match.group(4)
    value_quote = ""
    if len(raw_value) >= 2 and raw_value[0] in {'"', "'"} and raw_value[-1] == raw_value[0]:
        value_quote = raw_value[0]
    return (
        f"{key_quote}{match.group(2)}{key_quote}{match.group(3)}"
        f"{value_quote}{REDACTED}{value_quote}"
    )


def is_sensitive_key(key: str) -> bool:
    """Return whether a structured field name should be masked."""
    normalized = key.lower().replace(REDACTION_SOURCE_SEPARATOR, REDACTION_NORMALIZED_SEPARATOR)
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)
