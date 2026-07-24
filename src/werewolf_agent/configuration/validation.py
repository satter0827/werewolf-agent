"""Validation helpers for runtime inputs."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from werewolf_agent.configuration.constants import (
    GENERATED_PLAYER_ID_PREFIX,
    GENERATED_PLAYER_ID_SEPARATOR,
    GENERATED_PLAYER_NAME_PREFIX,
    GENERATED_PLAYER_NAME_SEPARATOR,
    GENERATED_PLAYER_NUMBER_START,
    PUBLIC_PLAYER_LABEL_PREFIX,
)
from werewolf_agent.configuration.messages import (
    MESSAGE_GENERATED_PLAYER_INDEX_MUST_BE_AT_LEAST_ONE,
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


def generated_player_id(index: int) -> str:
    """Return the generated player id for a one-based table seat."""
    if index < GENERATED_PLAYER_NUMBER_START:
        raise ValueError(MESSAGE_GENERATED_PLAYER_INDEX_MUST_BE_AT_LEAST_ONE)
    return f"{GENERATED_PLAYER_ID_PREFIX}{GENERATED_PLAYER_ID_SEPARATOR}{index}"


def generated_player_name(index: int) -> str:
    """Return the generated display name for a one-based table seat."""
    if index < GENERATED_PLAYER_NUMBER_START:
        raise ValueError(MESSAGE_GENERATED_PLAYER_INDEX_MUST_BE_AT_LEAST_ONE)
    return f"{GENERATED_PLAYER_NAME_PREFIX}{GENERATED_PLAYER_NAME_SEPARATOR}{index}"


def generated_player_ids(player_count: int) -> set[str]:
    """Return every generated player id for a table size."""
    if player_count < GENERATED_PLAYER_NUMBER_START:
        return set()
    return {
        generated_player_id(index)
        for index in range(GENERATED_PLAYER_NUMBER_START, player_count + 1)
    }


def generated_player_number(value: object) -> str | None:
    """Return the generated player number suffix, if the value is a generated id."""
    text = str(value)
    prefix = f"{GENERATED_PLAYER_ID_PREFIX}{GENERATED_PLAYER_ID_SEPARATOR}"
    if not text.startswith(prefix):
        return None
    suffix = text.removeprefix(prefix)
    return suffix if suffix.isdigit() else None


def generated_player_name_number(value: object) -> str | None:
    """Return the generated player name suffix, if the value is a generated name."""
    text = str(value).strip()
    prefix = f"{GENERATED_PLAYER_NAME_PREFIX}{GENERATED_PLAYER_NAME_SEPARATOR}"
    if not text.startswith(prefix):
        return None
    suffix = text.removeprefix(prefix).strip()
    return suffix if suffix.isdigit() else None


def public_generated_player_label(value: object) -> str | None:
    """Return a compact public label for a generated player id."""
    suffix = generated_player_number(value)
    if suffix is None:
        return None
    return f"{PUBLIC_PLAYER_LABEL_PREFIX}{suffix}"


def public_generated_player_name_label(value: object) -> str | None:
    """Return a compact public label for a generated player display name."""
    suffix = generated_player_name_number(value)
    if suffix is None:
        return None
    return f"{PUBLIC_PLAYER_LABEL_PREFIX}{suffix}"
