"""品質成果物manifestの契約。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts._infra.process import utc_now
from scripts.quality import artifacts
from scripts.quality.artifacts import (
    manifest_paths,
    validate_references,
    validate_retention_capacity,
    write_manifest,
)
from scripts.quality.models import GateResult, RunContext
from scripts.quality.reporting import write_summary


def test_manifest_records_review_evidence_and_diagnostics(tmp_path: Path) -> None:
    """人とAIが成果物の出所、分類、hashを追跡できる。"""
    (tmp_path / "test-results").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "test-results" / "quick.json").write_text("{}", encoding="utf-8")
    (tmp_path / "logs" / "pytest.log").write_text("passed", encoding="utf-8")
    results = [
        GateResult(
            "pytest",
            "Python test",
            "passed",
            1.0,
            log="logs/pytest.log",
            artifacts=["test-results/quick.json"],
        )
    ]

    manifest = write_manifest(tmp_path, results)
    document = json.loads(manifest.read_text(encoding="utf-8"))
    entries = {entry["path"]: entry for entry in document["artifacts"]}

    assert entries["test-results/quick.json"]["category"] == "evidence"
    assert entries["test-results/quick.json"]["producer"] == "pytest"
    assert entries["logs/pytest.log"]["category"] == "diagnostic"
    assert len(entries["logs/pytest.log"]["sha256"]) == 64
    assert manifest_paths(manifest) == {
        "logs/pytest.log",
        "test-results/quick.json",
    }


def test_video_is_reproducible_even_under_browser_evidence_root() -> None:
    assert artifacts.artifact_category(Path("browser/trace.webm")) == "reproducible"


def test_manifest_hashes_final_redacted_report(tmp_path: Path) -> None:
    """manifestはredact前の内容ではなく公開する最終内容を指す。"""
    for relative in ("test-results", "coverage", "benchmarks", "browser"):
        (tmp_path / relative).mkdir()
    context = RunContext(
        profile="quick",
        jobs=1,
        timeout_seconds=1,
        run_id="run",
        run_dir=tmp_path,
        environment={},
        initial_git_status="token=secret-value",
        started_at=utc_now(),
    )
    result = GateResult("gate", "Gate", "failed", 0.0, message="token=secret-value")

    write_summary(context, [result])

    report = tmp_path / "report.json"
    document = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    entry = next(item for item in document["artifacts"] if item["path"] == "report.json")
    assert "secret-value" not in report.read_text(encoding="utf-8")
    assert entry["sha256"] == hashlib.sha256(report.read_bytes()).hexdigest()


def test_missing_report_reference_is_an_artifact_contract_violation(tmp_path: Path) -> None:
    """保持後に開けないartifact参照を成功扱いにしない。"""
    results = [
        GateResult(
            "browser",
            "Browser",
            "passed",
            1.0,
            artifacts=["browser/results.json"],
        )
    ]

    assert validate_references(tmp_path, results) == [
        "browserの成果物参照が存在しません: browser/results.json"
    ]


def test_protected_evidence_over_capacity_is_a_contract_violation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "pyproject.toml").write_text(
        "[tool.werewolf-quality]\nfailure_run_max_mib = 1\n", encoding="utf-8"
    )
    run = tmp_path / "run"
    (run / "test-results").mkdir(parents=True)
    (run / "test-results" / "large.json").write_bytes(b"x" * (1024 * 1024 + 1))
    monkeypatch.setattr(artifacts, "REPOSITORY_ROOT", repository)

    assert validate_retention_capacity(run) == [
        "必須証拠 1048577 bytes が保持上限 1048576 bytes を超えています。"
    ]
