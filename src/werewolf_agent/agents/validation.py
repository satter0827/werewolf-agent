"""Agent-owned input normalization helpers."""

from __future__ import annotations

from typing import TypeGuard

DISCUSSION_WHITESPACE = frozenset(" \t\n\r\f\v")


def non_blank(value: object, field_name: str) -> str:
    """Return a stripped non-empty string."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def optional_non_blank(value: object | None, field_name: str) -> str | None:
    """Return a stripped optional non-empty string."""
    if value is None:
        return None
    return non_blank(value, field_name)


def is_discussion_utterance(value: object) -> TypeGuard[str]:
    """Return whether a value contains non-contract-whitespace content."""
    return isinstance(value, str) and any(
        character not in DISCUSSION_WHITESPACE for character in value
    )


def validate_discussion_utterance(value: object) -> str:
    """Preserve an utterance while rejecting explicit ASCII-whitespace blanks."""
    if not isinstance(value, str):
        raise ValueError("utterance must be a string")
    if not is_discussion_utterance(value):
        raise ValueError("utterance must not be blank")
    return value
