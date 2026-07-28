"""Docs品質gateの成果物契約を検査する。"""

import json
from pathlib import Path

import pytest
from scripts.quality import runner as quality
from scripts.quality.gates import documentation


def test_failed_docs_build_keeps_structured_diagnostic_in_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """失敗したbuildを正常buildから分離してfailure保持対象へ置く。"""
    report_path = tmp_path / "shared" / "docs-inspection.json"
    report_path.parent.mkdir()
    report_path.write_text(
        json.dumps({"status": "failed", "findings": [{"message": "warning"}]}),
        encoding="utf-8",
    )
    run_dir = tmp_path / "run"
    (run_dir / "logs").mkdir(parents=True)
    context = quality.RunContext(
        profile="check",
        jobs=1,
        timeout_seconds=60,
        run_id="run",
        run_dir=run_dir,
        environment={},
        started_at=quality.utc_now(),
    )
    monkeypatch.setattr(
        documentation,
        "build_documentation",
        lambda: (1, report_path),
    )
    gate = documentation.build()[0]

    result = quality._run_gate(context, gate)

    assert result.state == "failed"
    assert result.artifacts == ["docs/report.json"]
    assert (
        json.loads((run_dir / "docs" / "report.json").read_text(encoding="utf-8"))["status"]
        == "failed"
    )
