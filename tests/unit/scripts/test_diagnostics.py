"""最新成果物から生成するdiagnostics view。"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

from scripts._infra.artifacts import ArtifactLayout
from scripts.diagnostics import collector


def test_collect_references_existing_artifacts_without_copying_raw_logs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    layout = ArtifactLayout(tmp_path / ".werewolf-agent")
    operation = layout.operations / "environment" / "run-1"
    operation.mkdir(parents=True)
    (operation / "report.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "state": "blocked",
                "confirmed_causes": ["Docker daemonへ接続できません。"],
                "unconfirmed_scope": ["後続検査は未確認です。"],
                "next_actions": ["Docker Desktopを起動してください。"],
            }
        ),
        encoding="utf-8",
    )
    log_root = layout.logs / "application"
    log_root.mkdir(parents=True)
    (log_root / "api.jsonl").write_text(
        '{"@timestamp":"2026-01-01T00:00:00Z","log.level":"ERROR",'
        '"trace.id":"trace-1","event.action":"api.request.failed",'
        '"error.code":"internal.unexpected"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(collector, "LAYOUT", layout)
    monkeypatch.setattr(collector, "REPOSITORY_ROOT", tmp_path)

    @contextmanager
    def staged(_name: str):
        root = tmp_path / "staged"
        root.mkdir()
        yield root

    monkeypatch.setattr(collector, "staged_directory", staged)
    report_path = collector.collect()
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["state"] == "blocked"
    assert report["confirmed_causes"][0]["detail"] == "Docker daemonへ接続できません。"
    assert report["correlation_ids"]["trace_ids"] == ["trace-1"]
    log_observation = next(
        item for item in report["observations"] if item["source"].endswith("api.jsonl")
    )
    assert log_observation["event_actions"] == {"api.request.failed": 1}
    assert log_observation["error_codes"] == {"internal.unexpected": 1}
    assert not (report_path.parent / "api.jsonl").exists()
    assert report["related_artifacts"][0]["sha256"]


def test_latest_reports_keeps_quality_profiles_and_nested_review_kinds_separate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    layout = ArtifactLayout(tmp_path / ".werewolf-agent")
    paths = (
        layout.quality / "profiles" / "check" / "current" / "report.json",
        layout.quality / "profiles" / "release" / "current" / "report.json",
        layout.reviews / "agents" / "runs" / "run-1" / "report.json",
    )
    for path in paths:
        path.parent.mkdir(parents=True)
        path.write_text('{"state":"passed"}', encoding="utf-8")
    monkeypatch.setattr(collector, "LAYOUT", layout)
    monkeypatch.setattr(collector, "REPOSITORY_ROOT", tmp_path)

    related = collector._latest_reports()

    assert {item["kind"] for item in related} == {
        "quality/profiles/check",
        "quality/profiles/release",
        "reviews/agents/runs",
    }


def test_collect_rejects_report_that_does_not_match_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    layout = ArtifactLayout(tmp_path / ".werewolf-agent")
    operation = layout.operations / "environment" / "run-1"
    operation.mkdir(parents=True)
    (operation / "report.json").write_text(
        '{"state":"passed","confirmed_causes":[]}', encoding="utf-8"
    )
    (operation / "manifest.json").write_text(
        json.dumps(
            {
                "artifacts": [
                    {"path": "report.json", "sha256": "0" * 64},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(collector, "LAYOUT", layout)
    monkeypatch.setattr(collector, "REPOSITORY_ROOT", tmp_path)

    @contextmanager
    def staged(_name: str):
        root = tmp_path / "staged"
        root.mkdir()
        yield root

    monkeypatch.setattr(collector, "staged_directory", staged)

    report = json.loads(collector.collect().read_text(encoding="utf-8"))

    assert report["state"] == "error"
    assert report["observations"][0]["state"] == "corrupted"
    assert "SHA-256" in report["confirmed_causes"][0]["detail"]
