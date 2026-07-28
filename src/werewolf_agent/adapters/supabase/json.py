"""Supabase JSON parameter conversion."""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb


def jsonb(value: Any) -> Jsonb:
    """Return a psycopg JSONB parameter without leaking psycopg into callers."""
    return Jsonb(value)


__all__ = ["jsonb"]
