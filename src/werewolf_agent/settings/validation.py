"""Validation helpers for runtime inputs."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from werewolf_agent.settings.messages import (
    message_field_must_be_one_of,
    message_field_must_be_string,
    message_field_must_not_be_blank,
)


def non_blank(value: str, field_name: str) -> str:
    """Return a stripped non-empty string."""
    normalized = value.strip()
    if not normalized:
        raise ValueError(message_field_must_not_be_blank(field_name))
    return normalized


def optional_non_blank(value: str | None, field_name: str) -> str | None:
    """Return a stripped optional non-empty string."""
    if value is None:
        return None
    return non_blank(value, field_name)


def normalize_non_blank(value: object, *, field_name: str) -> str:
    """Return a stripped non-empty string from unknown input."""
    if not isinstance(value, str):
        raise ValueError(message_field_must_be_string(field_name))
    return non_blank(value, field_name)


def normalize_choice(
    value: object,
    *,
    field_name: str,
    choices: Iterable[str],
    case: Literal["upper", "lower"],
) -> str:
    """Return a validated string choice normalized to the configured case."""
    if not isinstance(value, str):
        raise ValueError(message_field_must_be_string(field_name))

    choice_set = frozenset(choices)
    normalized = value.strip().upper() if case == "upper" else value.strip().lower()
    if normalized not in choice_set:
        raise ValueError(message_field_must_be_one_of(field_name, choice_set))
    return normalized
