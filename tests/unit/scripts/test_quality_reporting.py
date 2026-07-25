"""品質runnerの公開仕様を検査する。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from scripts.quality import reporting
from scripts.quality import runner as quality

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        (["passed", "blocked"], "blocked"),
        (["blocked", "failed"], "failed"),
        (["blocked", "failed", "error"], "error"),
    ],
)
def test_run_state_preserves_the_most_actionable_failure(
    states: list[quality.State],
    expected: quality.State,
) -> None:
    """環境不足によって品質違反やrunner異常を隠さない。"""
    results = [
        quality.GateResult(str(index), "gate", state, 0.0) for index, state in enumerate(states)
    ]

    assert reporting.result_state(results) == expected


def test_events_include_skipped_gates(tmp_path: Path) -> None:
    """途中停止後の未実行gateもAIが追跡できるeventへ残す。"""

    event_path = tmp_path / "events.jsonl"
    result = quality.GateResult(
        name="integration",
        description="Integration",
        state="skipped",
        duration_seconds=0.0,
        message="前段の品質ゲートが完了しませんでした。",
    )

    quality._append_events(event_path, [result])

    event = json.loads(event_path.read_text(encoding="utf-8"))
    assert event["gate"] == "integration"
    assert event["state"] == "skipped"
    assert event["message"]


def test_run_metrics_are_machine_readable_and_human_summarized(tmp_path: Path) -> None:
    """JUnit、coverage、benchmark、browser成果物を最上位reportへ集約する。"""

    for relative in ("test-results", "coverage", "benchmarks", "browser"):
        (tmp_path / relative).mkdir()
    (tmp_path / "test-results" / "quick.xml").write_text(
        '<testsuites><testsuite tests="7" failures="1" errors="1" skipped="1">'
        '<testsuite tests="5" failures="1" errors="0" skipped="1"/>'
        '<testsuite tests="2" failures="0" errors="1" skipped="0"/>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    (tmp_path / "coverage" / "coverage.xml").write_text(
        '<coverage lines-valid="80" lines-covered="64" branches-valid="20" '
        'branches-covered="10" line-rate="0.8" branch-rate="0.5"/>',
        encoding="utf-8",
    )
    (tmp_path / "benchmarks" / "core.json").write_text(
        json.dumps({"benchmarks": [{"name": "core", "stats": {"mean": 0.00125, "rounds": 8}}]}),
        encoding="utf-8",
    )
    (tmp_path / "browser" / "desktop.png").write_bytes(b"image")

    metrics, issues = reporting.collect_run_metrics(tmp_path)
    summary = "\n".join(reporting._metric_summary(metrics, issues))

    assert issues == []
    assert metrics["tests"]["quick"] == {
        "tests": 7,
        "failures": 1,
        "errors": 1,
        "skipped": 1,
        "passed": 4,
    }
    assert metrics["coverage"] == {
        "total_percent": 74.0,
        "line_percent": 80.0,
        "branch_percent": 50.0,
        "lines": {"covered": 64, "valid": 80},
        "branches": {"covered": 10, "valid": 20},
    }
    assert metrics["benchmarks"] == [{"name": "core", "mean_ms": 1.25, "rounds": 8}]
    assert metrics["browser_artifacts"] == ["browser/desktop.png"]
    assert "coverage: total 74.0%, line 80.0%, branch 50.0%" in summary
    assert "benchmark `core`: mean 1.25ms, 8 rounds" in summary


def test_run_metrics_report_malformed_artifacts_without_breaking_summary(
    tmp_path: Path,
) -> None:
    """失敗時の壊れた成果物もreport生成を妨げず調査対象として残す。"""

    for relative in ("test-results", "coverage", "benchmarks", "browser"):
        (tmp_path / relative).mkdir()
    (tmp_path / "test-results" / "quick.xml").write_text("<broken", encoding="utf-8")
    (tmp_path / "coverage" / "coverage.xml").write_text("<broken", encoding="utf-8")
    (tmp_path / "benchmarks" / "core.json").write_text("{broken", encoding="utf-8")

    metrics, issues = reporting.collect_run_metrics(tmp_path)

    assert metrics["tests"] == {}
    assert len(issues) == 3
    assert {issue.split("を", maxsplit=1)[0] for issue in issues} == {
        "quick.xml",
        "coverage.xml",
        "core.json",
    }


def test_artifact_issues_change_final_state_and_exit_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """成果物解析不能をpassedにせず最上位errorへ反映する。"""

    for relative in ("test-results", "coverage", "benchmarks", "browser"):
        (tmp_path / relative).mkdir()
    (tmp_path / "test-results" / "quick.xml").write_text("<broken", encoding="utf-8")
    context = quality.RunContext(
        profile="quick",
        jobs=1,
        timeout_seconds=60,
        run_id="run",
        run_dir=tmp_path,
        environment={},
        initial_git_status="",
        started_at=quality.utc_now(),
    )
    results = [
        quality.GateResult(
            name="pytest",
            description="Python quick test",
            state="passed",
            duration_seconds=1.0,
        )
    ]

    state, report_path = quality._write_summary(context, results)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    events = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert state == "error"
    assert report["state"] == "error"
    assert report["results"][-1]["name"] == "artifact-validation"
    assert report["results"][-1]["state"] == "error"
    assert events[-1]["gate"] == "artifact-validation"


def test_profiles_require_their_declared_artifacts(
    tmp_path: Path,
) -> None:
    """0終了だけで合格させずgate自身の成果物契約を要求する。"""
    context = quality.RunContext(
        profile="quick",
        jobs=1,
        timeout_seconds=60,
        run_id="run",
        run_dir=tmp_path,
        environment={},
        initial_git_status="",
        started_at=quality.utc_now(),
    )
    gate = quality.Gate(
        "pytest",
        "Python quick test",
        artifacts=("test-results/quick.xml",),
    )

    issues, artifacts = quality._artifact_contract(context, gate)

    assert issues == ["成果物がありません: test-results/quick.xml"]
    assert artifacts == []


def test_required_artifacts_must_be_updated_by_the_current_run(tmp_path: Path) -> None:
    """前回runの成果物を今回の成功証拠として受理しない。"""

    run_dir = tmp_path / "run"
    result_path = run_dir / "test-results" / "quick.xml"
    result_path.parent.mkdir(parents=True)
    result_path.write_text("<testsuites/>", encoding="utf-8")
    os.utime(result_path, (1, 1))

    context = quality.RunContext(
        profile="quick",
        jobs=1,
        timeout_seconds=60,
        run_id="run",
        run_dir=run_dir,
        environment={},
        initial_git_status="",
        started_at=quality.utc_now(),
    )
    gate = quality.Gate("pytest", "Python quick test", artifacts=("test-results/quick.xml",))

    issues, artifacts = quality._artifact_contract(context, gate)

    assert issues == ["成果物が現在runで更新されていません: test-results/quick.xml"]
    assert artifacts == ["test-results/quick.xml"]
