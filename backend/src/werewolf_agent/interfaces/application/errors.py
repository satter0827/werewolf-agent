"""Application bridge errors consumed by interface adapters."""

from __future__ import annotations


class ResourceNotFoundError(Exception):
    """Raised when an interface-facing resource cannot be found."""
