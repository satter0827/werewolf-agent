"""Wire-contract naming and input normalization helpers."""

from __future__ import annotations

from werewolf_agent.contracts.constants import (
    GENERATED_PLAYER_ID_PREFIX,
    GENERATED_PLAYER_ID_SEPARATOR,
    GENERATED_PLAYER_NAME_PREFIX,
    GENERATED_PLAYER_NAME_SEPARATOR,
    GENERATED_PLAYER_NUMBER_START,
    PUBLIC_PLAYER_LABEL_PREFIX,
)


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


def generated_player_id(index: int) -> str:
    """Return the generated player id for a one-based table seat."""
    if index < GENERATED_PLAYER_NUMBER_START:
        raise ValueError("generated player index must be at least 1")
    return f"{GENERATED_PLAYER_ID_PREFIX}{GENERATED_PLAYER_ID_SEPARATOR}{index}"


def generated_player_ids(player_count: int) -> set[str]:
    """Return every generated player id for a table size."""
    if player_count < GENERATED_PLAYER_NUMBER_START:
        return set()
    return {
        generated_player_id(index)
        for index in range(GENERATED_PLAYER_NUMBER_START, player_count + 1)
    }


def generated_player_name(index: int) -> str:
    """Return the generated display name for a one-based table seat."""
    if index < GENERATED_PLAYER_NUMBER_START:
        raise ValueError("generated player index must be at least 1")
    return f"{GENERATED_PLAYER_NAME_PREFIX}{GENERATED_PLAYER_NAME_SEPARATOR}{index}"


def public_generated_player_label(value: object) -> str | None:
    """Return a compact public label for a generated player id."""
    text = str(value)
    prefix = f"{GENERATED_PLAYER_ID_PREFIX}{GENERATED_PLAYER_ID_SEPARATOR}"
    if not text.startswith(prefix):
        return None
    suffix = text.removeprefix(prefix)
    if not suffix.isdigit():
        return None
    return f"{PUBLIC_PLAYER_LABEL_PREFIX}{suffix}"
