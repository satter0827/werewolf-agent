"""Domain規則とFake providerの実装境界。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "src" / "werewolf_agent"
FRONTEND = ROOT / "frontend" / "src"


def test_domain_rules_and_fake_provider_remain_centralized() -> None:
    handlers = (PACKAGE / "usecase" / "handlers.py").read_text(encoding="utf-8")
    for legacy_function in ("start_game", "submit_action", "advance_phase", "observe"):
        assert f"{legacy_function}(" not in handlers
    service = (PACKAGE / "agents" / "langchain" / "service.py").read_text(encoding="utf-8")
    assert "from langchain_core.language_models.fake import FakeListLLM" in service
    assert "class Fake" not in service
