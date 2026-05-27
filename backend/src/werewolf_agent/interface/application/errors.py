"""Application bridge errors raised before HTTP translation."""

from __future__ import annotations


class ResourceNotFoundError(Exception):
    """Raised when a requested resource does not exist."""
