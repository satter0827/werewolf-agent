"""Private model and validation helpers for the domain."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Immutable model that rejects undeclared fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def non_blank(value: str, field_name: str) -> str:
    """Normalize a required identifier or text value."""
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank.")
    return normalized


def optional_non_blank(value: str | None, field_name: str) -> str | None:
    """Normalize an optional identifier or text value."""
    return None if value is None else non_blank(value, field_name)
