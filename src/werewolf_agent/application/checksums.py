"""Canonical checksums for immutable application payloads."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def checksum_payload(payload: Any) -> str:
    """Return a stable SHA-256 checksum for JSON-compatible data."""
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = ["checksum_payload"]
