"""品質成果物の状態別保持契約。"""

import json
from pathlib import Path

import pytest
from scripts._infra.artifacts import ArtifactLayout
from scripts.quality import retention


def _run(root: Path, name: str, state: str) -> Path:
    run = root / name
    run.mkdir()
    (run / "report.json").write_text(
        json.dumps({"run_id": name, "state": state}),
        encoding="utf-8",
    )
    (run / "summary.md").write_text(f"# {name}\n", encoding="utf-8")
    return run


def test_success_replaces_latest_without_growing_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """成功結果をselectorごとの最新値へ圧縮する。"""
    monkeypatch.setattr(retention, "LAYOUT", ArtifactLayout(tmp_path / "artifacts"))

    first_run = _run(tmp_path, "first", "passed")
    (first_run / "events.jsonl").write_text("{}\n", encoding="utf-8")
    first = retention.publish_run(first_run, "quick", "passed")
    second_run = _run(tmp_path, "second", "passed")
    (second_run / "events.jsonl").write_text("{}\n", encoding="utf-8")
    second = retention.publish_run(second_run, "quick", "passed")

    assert first == second
    assert json.loads(second.read_text(encoding="utf-8"))["run_id"] == "second"
    assert (second.parent / "events.jsonl").is_file()
    assert len(list(second.parent.iterdir())) == 3


def test_failures_are_bounded_per_selector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非成功結果を設定件数より増やさない。"""
    monkeypatch.setattr(retention, "LAYOUT", ArtifactLayout(tmp_path / "artifacts"))

    for index in range(retention.FAILURES_PER_SELECTOR + 2):
        retention.publish_run(
            _run(tmp_path, f"run-{index}", "failed"),
            "quick",
            "failed",
        )

    failures = tmp_path / "artifacts" / "quality" / "failures" / "quick"
    assert len(list(failures.iterdir())) == retention.FAILURES_PER_SELECTOR


def test_failure_keeps_complete_review_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """失敗に至る成功gateのlogとevent streamも保持する。"""
    monkeypatch.setattr(retention, "LAYOUT", ArtifactLayout(tmp_path / "artifacts"))
    run = _run(tmp_path, "run", "failed")
    (run / "logs").mkdir()
    (run / "logs" / "passed.log").write_text("passed", encoding="utf-8")
    (run / "logs" / "failed.log").write_text("failed", encoding="utf-8")
    (run / "events.jsonl").write_text("{}\n", encoding="utf-8")
    (run / "test-results").mkdir()
    (run / "test-results" / "unit.xml").write_text("<testsuites/>", encoding="utf-8")
    (run / "report.json").write_text(
        json.dumps(
            {
                "run_id": "run",
                "state": "failed",
                "results": [
                    {"name": "ruff", "state": "passed", "log": "logs/passed.log"},
                    {"name": "mypy", "state": "failed", "log": "logs/failed.log"},
                ],
            }
        ),
        encoding="utf-8",
    )

    report = retention.publish_run(run, "quick", "failed")

    assert (report.parent / "logs" / "failed.log").is_file()
    assert (report.parent / "test-results" / "unit.xml").is_file()
    assert (report.parent / "logs" / "passed.log").is_file()
    assert (report.parent / "events.jsonl").is_file()
    retained = json.loads(report.read_text(encoding="utf-8"))["retention"]
    assert retained["omitted_count"] == 0
    assert retained["limit_exceeded"] is False


def test_abandoned_run_is_recovered_before_next_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "runtime"
    run = runtime / "quality" / "runs" / "20260726T000000Z-quick-1"
    (run / "logs").mkdir(parents=True)
    (run / "logs" / "partial.log").write_text("partial", encoding="utf-8")
    monkeypatch.setattr(retention, "TEMPORARY_ROOT", runtime)
    monkeypatch.setattr(retention, "LAYOUT", ArtifactLayout(tmp_path / "artifacts"))

    recovered = retention.recover_abandoned_runs(now=run.stat().st_mtime + 600)

    assert len(recovered) == 1
    assert (recovered[0] / "logs" / "partial.log").is_file()
    assert (recovered[0] / "manifest.json").is_file()
    assert (
        json.loads((recovered[0] / "report.json").read_text(encoding="utf-8"))["state"] == "error"
    )


def test_live_run_is_not_recovered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = tmp_path / "runtime"
    run = runtime / "quality" / "runs" / "20260726T000000Z-deep-1"
    run.mkdir(parents=True)
    monkeypatch.setattr(retention, "TEMPORARY_ROOT", runtime)
    monkeypatch.setattr(retention, "LAYOUT", ArtifactLayout(tmp_path / "artifacts"))
    retention.mark_run_active(run)

    recovered = retention.recover_abandoned_runs(now=run.stat().st_mtime + 600)

    assert recovered == []
    assert run.is_dir()
