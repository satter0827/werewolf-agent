"""Agent-owned input normalization helpers."""

from __future__ import annotations


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
