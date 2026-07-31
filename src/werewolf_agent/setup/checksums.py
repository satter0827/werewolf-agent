"""Setupと実験入力に使う正規checksumを定義する."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def checksum_payload(payload: Any) -> str:
    """JSON互換値の安定したSHA-256 checksumを返す."""
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = ["checksum_payload"]
