"""Shared immutable configuration model base classes."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Frozen model that rejects undeclared fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)


__all__ = ["StrictModel"]
