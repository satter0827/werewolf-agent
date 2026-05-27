"""Pytest configuration for local Windows-friendly temporary files."""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Iterator[Path]:
    """Create test temp directories without pytest's restrictive Windows ACLs."""
    root = Path(__file__).resolve().parents[1] / ".pytest-tmp"
    root.mkdir(exist_ok=True)
    path = root / f"{request.node.name[:40]}-{uuid.uuid4().hex}"
    path.mkdir()

    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
