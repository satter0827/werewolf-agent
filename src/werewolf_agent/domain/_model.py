"""Immutable collection and validation helpers owned by the domain."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from types import MappingProxyType
from typing import Any, Generic, TypeVar

_K = TypeVar("_K")
_V = TypeVar("_V")


class FrozenDict(Mapping[_K, _V], Generic[_K, _V]):
    """Small immutable mapping used by public domain values."""

    __slots__ = ("_values",)

    def __init__(self, values: Mapping[_K, _V] | None = None) -> None:
        self._values = MappingProxyType(dict(values or {}))

    def __getitem__(self, key: _K) -> _V:
        return self._values[key]

    def __iter__(self) -> Iterator[_K]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __repr__(self) -> str:
        return f"FrozenDict({self._values!r})"

    def __copy__(self) -> FrozenDict[_K, _V]:
        """Return this immutable mapping for a shallow copy."""
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> FrozenDict[_K, _V]:
        """Return this recursively immutable mapping for a deep copy."""
        memo[id(self)] = self
        return self


def frozen_mapping(values: Mapping[_K, _V] | None = None) -> FrozenDict[_K, _V]:
    """Return an immutable defensive copy of a mapping."""
    return FrozenDict(values)


def freeze_value(value: Any) -> Any:
    """Recursively freeze JSON-like collection values."""
    if isinstance(value, Mapping):
        return FrozenDict({key: freeze_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze_value(item) for item in value)
    return value


def non_blank(value: str, field_name: str) -> str:
    """Normalize a required identifier or text value."""
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank.")
    return normalized


def optional_non_blank(value: str | None, field_name: str) -> str | None:
    """Normalize an optional identifier or text value."""
    return None if value is None else non_blank(value, field_name)


__all__ = ["FrozenDict", "freeze_value", "frozen_mapping", "non_blank", "optional_non_blank"]
