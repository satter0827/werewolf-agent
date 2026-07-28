"""品質schedulerの実行時依存契約を検査する。"""

from pathlib import Path

import pytest
from scripts.quality import retention
from scripts.quality import runner as quality


def test_unrelated_gate_continues_after_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """失敗gateへ依存しない後続gateは実行を継続する。"""
    for relative in ("logs", "test-results", "coverage", "benchmarks", "browser"):
        (tmp_path / relative).mkdir()
    stages = [
        [quality.Gate("failed", "failed")],
        [quality.Gate("independent", "independent")],
        [quality.Gate("dependent", "dependent", dependencies=("failed",))],
    ]
    executed: list[str] = []

    def run_gate(
        _context: quality.RunContext,
        gate: quality.Gate,
    ) -> quality.GateResult:
        executed.append(gate.name)
        state = "failed" if gate.name == "failed" else "passed"
        return quality.GateResult(gate.name, gate.description, state, 0.0)

    monkeypatch.setattr(
        quality,
        "create_run_directory",
        lambda _profile: ("run", tmp_path),
    )
    monkeypatch.setattr(quality, "quality_environment", lambda **_kwargs: {})
    monkeypatch.setattr(quality, "_run_gate", run_gate)
    monkeypatch.setattr(
        retention,
        "publish_run",
        lambda run_dir, _selector, _state: run_dir / "report.json",
    )

    state, report_path = quality.execute(
        "focus",
        jobs=1,
        timeout_seconds=1,
        stages_override=stages,
    )

    assert state == "failed"
    assert report_path == tmp_path / "report.json"
    assert executed == ["failed", "independent"]
