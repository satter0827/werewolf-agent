"""品質gateの内容fingerprintと証跡再利用契約。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from scripts._infra.artifacts import ArtifactLayout
from scripts.quality import reuse
from scripts.quality.models import Gate, RunContext


def _context(root: Path) -> RunContext:
    run = root / "run"
    run.mkdir()
    return RunContext(
        profile="check",
        jobs=1,
        timeout_seconds=10,
        run_id="current",
        run_dir=run,
        environment={},
        initial_git_status="",
        started_at=datetime.now(UTC),
        initial_dependency_fingerprint="dependencies",
    )


def test_gate_fingerprint_changes_with_declared_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "src" / "module.py"
    source.parent.mkdir()
    source.write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setattr(reuse, "REPOSITORY_ROOT", tmp_path)
    gate = Gate("ruff", "lint", ("ruff", "check"), inputs=("src/**/*.py",), reusable=True)
    context = _context(tmp_path)

    before = reuse.gate_fingerprint(context, gate)
    source.write_text("value = 2\n", encoding="utf-8")

    assert reuse.gate_fingerprint(context, gate) != before


def test_reuse_requires_matching_success_and_copies_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    layout = ArtifactLayout(tmp_path / "artifacts")
    monkeypatch.setattr(reuse, "LAYOUT", layout)
    monkeypatch.setattr(reuse, "REPOSITORY_ROOT", tmp_path)
    source = tmp_path / "src" / "module.py"
    source.parent.mkdir()
    source.write_text("value = 1\n", encoding="utf-8")
    context = _context(tmp_path)
    gate = Gate("ruff", "lint", ("ruff", "check"), inputs=("src/**/*.py",), reusable=True)
    bundle = layout.quality / "profiles" / "check" / "current"
    (bundle / "logs").mkdir(parents=True)
    (bundle / "logs" / "ruff.log").write_text("passed\n", encoding="utf-8")
    (bundle / "report.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "name": "ruff",
                        "state": "passed",
                        "fingerprint": reuse.gate_fingerprint(context, gate),
                        "log": "logs/ruff.log",
                        "artifacts": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    pointer = layout.quality / "profiles" / "check" / "last-passed.json"
    pointer.write_text(
        json.dumps({"run_id": "previous", "report": "profiles/check/current/report.json"}),
        encoding="utf-8",
    )

    result = reuse.reuse_gate(context, gate)

    assert result is not None
    assert result.execution_origin == "reused"
    assert result.source_run == "previous"
    assert (context.run_dir / "logs" / "ruff.log").is_file()
