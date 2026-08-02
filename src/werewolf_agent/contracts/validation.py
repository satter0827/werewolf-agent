"""Wire-contract naming and input normalization helpers."""

from __future__ import annotations

DISCUSSION_WHITESPACE = frozenset(" \t\n\r\f\v")


def non_blank(value: str, field_name: str) -> str:
    """Return a stripped non-empty string."""
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def optional_non_blank(value: str | None, field_name: str) -> str | None:
    """Return a stripped optional non-empty string."""
    if value is None:
        return None
    return non_blank(value, field_name)


def validate_discussion_utterance(value: str) -> str:
    """Preserve display text while rejecting explicit ASCII-whitespace blanks."""
    if not any(character not in DISCUSSION_WHITESPACE for character in value):
        raise ValueError("utterance must not be blank")
    return value
