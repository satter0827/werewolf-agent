"""API entrypointの観測境界。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "src" / "werewolf_agent"


def test_api_entrypoint_uses_the_shared_redacting_log_pipeline() -> None:
    source = (PACKAGE / "api" / "app.py").read_text(encoding="utf-8")
    assert "configure_entrypoint_logging(" in source
    assert 'default_log_file_name="api.jsonl"' in source
