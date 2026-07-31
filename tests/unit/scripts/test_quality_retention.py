"""品質成果物の状態別保持契約。"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts._infra import artifacts
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


def test_success_updates_current_and_last_passed_without_growing_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """成功結果をselectorごとの最新値へ圧縮する。"""
    monkeypatch.setattr(retention, "LAYOUT", ArtifactLayout(tmp_path / "artifacts"))

    first_run = _run(tmp_path, "first", "passed")
    (first_run / "events.jsonl").write_text("{}\n", encoding="utf-8")
    first = retention.publish_run(first_run, "focus", "passed")
    second_run = _run(tmp_path, "second", "passed")
    (second_run / "events.jsonl").write_text("{}\n", encoding="utf-8")
    second = retention.publish_run(second_run, "focus", "passed")

    assert first == second
    assert json.loads(second.read_text(encoding="utf-8"))["run_id"] == "second"
    assert (second.parent / "events.jsonl").is_file()
    pointer = json.loads((second.parent.parent / "last-passed.json").read_text(encoding="utf-8"))
    assert pointer["run_id"] == "second"
    history = tmp_path / "artifacts" / "quality" / "history" / "focus"
    assert not history.exists() or list(history.iterdir()) == []


def test_failures_are_bounded_per_selector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非成功結果を設定件数より増やさない。"""
    monkeypatch.setattr(retention, "LAYOUT", ArtifactLayout(tmp_path / "artifacts"))

    for index in range(retention.FAILURES_PER_SELECTOR + 2):
        retention.publish_run(
            _run(tmp_path, f"run-{index}", "failed"),
            "focus",
            "failed",
        )

    history = tmp_path / "artifacts" / "quality" / "history" / "focus"
    current = tmp_path / "artifacts" / "quality" / "profiles" / "focus" / "current"
    assert len(list(history.iterdir())) == retention.FAILURES_PER_SELECTOR
    assert current.is_dir()


def test_publish_retries_transient_windows_directory_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windowsの短時間lockで最新bundleの公開を失敗させない。"""
    monkeypatch.setattr(retention, "LAYOUT", ArtifactLayout(tmp_path / "artifacts"))
    directory_attempts = 0
    original_replace = Path.replace

    def transient_replace(path: Path, destination: Path) -> Path:
        nonlocal directory_attempts
        if path.is_dir():
            directory_attempts += 1
            if directory_attempts == 1:
                raise PermissionError("temporarily locked")
        return original_replace(path, destination)

    monkeypatch.setattr(Path, "replace", transient_replace)
    monkeypatch.setattr(artifacts, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(artifacts, "time", SimpleNamespace(sleep=lambda _seconds: None))

    report = retention.publish_run(_run(tmp_path, "run", "passed"), "check", "passed")

    assert json.loads(report.read_text(encoding="utf-8"))["run_id"] == "run"
    assert directory_attempts == 2


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

    report = retention.publish_run(run, "focus", "failed")

    assert (report.parent / "logs" / "failed.log").is_file()
    assert (report.parent / "test-results" / "unit.xml").is_file()
    assert (report.parent / "logs" / "passed.log").is_file()
    assert (report.parent / "events.jsonl").is_file()
    assert "retention" not in json.loads(report.read_text(encoding="utf-8"))


def test_failure_updates_current_without_losing_last_passed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(retention, "LAYOUT", ArtifactLayout(tmp_path / "artifacts"))
    retention.publish_run(_run(tmp_path, "passed-run", "passed"), "check", "passed")

    current = retention.publish_run(_run(tmp_path, "failed-run", "failed"), "check", "failed")

    assert json.loads(current.read_text(encoding="utf-8"))["run_id"] == "failed-run"
    pointer_path = current.parent.parent / "last-passed.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert pointer["run_id"] == "passed-run"
    assert (tmp_path / "artifacts" / "quality" / pointer["report"]).is_file()


def test_abandoned_run_is_recovered_before_next_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "runtime"
    run = runtime / "quality" / "runs" / "20260726T000000Z-focus-1"
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
