"""Public narration template grammar and bounded rendering."""

from __future__ import annotations

from collections.abc import Mapping
from string import Formatter
from typing import Final

NARRATION_RENDER_MAX_CHARS: Final = 2048
NARRATION_TEMPLATE_MAX_CHARS: Final = 1024
NARRATION_TEMPLATE_FIELDS: Final = frozenset(
    {
        "day",
        "phase",
        "phase_label",
        "actor",
        "player_count",
        "eliminated_player",
        "killed_player",
        "winner",
        "winner_label",
    }
)


def narration_fields(template: str) -> set[str]:
    """Validate the non-evaluating template grammar and return its fields."""
    if len(template) > NARRATION_TEMPLATE_MAX_CHARS:
        raise ValueError("narration template is too long")
    fields: set[str] = set()
    for _, field_name, format_spec, conversion in Formatter().parse(template):
        if format_spec or conversion:
            raise ValueError("narration template formatting is not supported")
        if field_name is not None:
            fields.add(field_name)
    return fields


def render_narration(template: str, values: Mapping[str, object]) -> str:
    """Render allowlisted fields without allocating an unbounded intermediate string."""
    try:
        if narration_fields(template) - NARRATION_TEMPLATE_FIELDS:
            return ""
        parts: list[str] = []
        length = 0
        for literal, field_name, _, _ in Formatter().parse(template):
            value = "" if field_name is None else str(values[field_name])
            length += len(literal) + len(value)
            if length > NARRATION_RENDER_MAX_CHARS:
                return ""
            parts.extend((literal, value))
        return "".join(parts)
    except (KeyError, ValueError):
        return ""


__all__ = [
    "NARRATION_RENDER_MAX_CHARS",
    "NARRATION_TEMPLATE_FIELDS",
    "NARRATION_TEMPLATE_MAX_CHARS",
    "narration_fields",
    "render_narration",
]
